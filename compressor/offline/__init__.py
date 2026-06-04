import time

from compressor.cache import (
    get_offline_manifest_with_metadata,
    write_offline_manifest_with_metadata,
    get_template_mtime,
)
from compressor.conf import settings


class OfflineCompressor:
    def __init__(self):
        self.manifest = {}
        self.metadata = {}

    def load_manifest(self):
        self.manifest, self.metadata = get_offline_manifest_with_metadata()

    def should_force_full(self):
        timeout = settings.COMPRESS_OFFLINE_INCREMENTAL_TIMEOUT
        if not timeout:
            return False
        created_at = self.metadata.get("created_at")
        if created_at is None:
            return True
        return (time.time() - created_at) > timeout

    def get_changed_templates(self, all_template_paths):
        last_modified = self.metadata.get("last_modified", {})
        template_keys = self.metadata.get("template_keys", {})

        all_template_paths_set = set(all_template_paths)

        for path in list(last_modified.keys()):
            if path not in all_template_paths_set:
                keys = template_keys.pop(path, [])
                for key in keys:
                    self.manifest.pop(key, None)
                last_modified.pop(path, None)

        changed = []
        for path in all_template_paths:
            current_mtime = get_template_mtime(path)
            if current_mtime is None:
                continue
            stored_mtime = last_modified.get(path)
            if stored_mtime is None or current_mtime != stored_mtime:
                changed.append(path)
                keys = template_keys.pop(path, [])
                for key in keys:
                    self.manifest.pop(key, None)
                last_modified.pop(path, None)

        return changed

    def record_template_keys(self, template_path, keys):
        if "template_keys" not in self.metadata:
            self.metadata["template_keys"] = {}
        self.metadata["template_keys"][template_path] = list(keys)

    def record_template_mtime(self, template_path, mtime):
        if "last_modified" not in self.metadata:
            self.metadata["last_modified"] = {}
        self.metadata["last_modified"][template_path] = mtime

    def save_manifest(self):
        write_offline_manifest_with_metadata(self.manifest, self.metadata)

    def generate_manifest_incremental(self, all_template_paths):
        self.load_manifest()

        if self.should_force_full():
            self.manifest = {}
            self.metadata = {
                "created_at": time.time(),
                "last_modified": {},
                "template_keys": {},
            }
            return set(all_template_paths)

        if "created_at" not in self.metadata:
            self.metadata["created_at"] = time.time()

        changed = set(self.get_changed_templates(all_template_paths))
        return changed