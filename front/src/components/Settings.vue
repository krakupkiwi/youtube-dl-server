<script setup>
import { getAPIUrl } from '../utils'
import SvgIcon from './SvgIcon.vue'
import DirectoryBrowserModal from './DirectoryBrowserModal.vue'
</script>
<script>
export default {
  data: () => ({
    ageRestrictionEnabled: false,
    ageLimit: 18,
    downloadFolders: [],
    newFolderName: '',
    newFolderPath: '',
    loading: true,
    saving: false,
    toasts: [],
  }),
  mounted() {
    this.fetchSettings();
  },
  methods: {
    async fetchSettings() {
      this.loading = true;
      try {
        const url = getAPIUrl('api/settings', import.meta.env);
        const response = await fetch(url);
        if (!response.ok) throw new Error(response.statusText);
        const data = await response.json();
        if (data.age_limit !== null && data.age_limit !== undefined) {
          this.ageRestrictionEnabled = true;
          this.ageLimit = data.age_limit;
        } else {
          this.ageRestrictionEnabled = false;
        }
        this.downloadFolders = data.download_folders || [];
      } catch (error) {
        this.showToast(error.message || 'Could not load settings.', false);
      } finally {
        this.loading = false;
      }
    },
    async saveSettings() {
      this.saving = true;
      const age_limit = this.ageRestrictionEnabled ? Number(this.ageLimit) : null;
      try {
        const url = getAPIUrl('api/settings', import.meta.env);
        const response = await fetch(url, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ age_limit, download_folders: this.downloadFolders }),
        });
        const result = await response.json();
        if (!result.success) {
          this.showToast(result.message || 'Could not save settings.', false);
        } else {
          this.downloadFolders = result.download_folders || [];
          this.showToast('Settings saved.', true);
        }
      } catch (error) {
        this.showToast(error.message || 'Network error while saving settings.', false);
      } finally {
        this.saving = false;
      }
    },
    addFolder() {
      const name = this.newFolderName.trim();
      const path = this.newFolderPath.trim();
      if (!name) return;
      if (/[/\\,]/.test(name) || name === '.' || name === '..') {
        this.showToast("Folder names can't contain '/', '\\', or ',', and can't be '.' or '..'.", false);
        return;
      }
      if (path) {
        const isPosixAbs = path.startsWith('/') && path !== '/';
        const isWindowsAbs = /^[A-Za-z]:[\\/]/.test(path) && path.length > 3;
        if (!(isPosixAbs || isWindowsAbs) || path.split(/[\\/]/).includes('..')) {
          this.showToast("Container path must be absolute (e.g. /concerts), not the root, and contain no '..' segments.", false);
          return;
        }
      }
      if (this.downloadFolders.some(f => f.name === name)) {
        this.showToast('That folder is already in the list.', false);
        return;
      }
      this.downloadFolders.push({ name, path: path || null });
      this.newFolderName = '';
      this.newFolderPath = '';
    },
    removeFolder(index) {
      this.downloadFolders.splice(index, 1);
    },
    openBrowser() {
      this.$refs.dirBrowser.open(this.newFolderPath);
    },
    onFolderPathSelected(path) {
      this.newFolderPath = path;
    },
    showToast(message, success = true) {
      const id = Date.now() + Math.random();
      this.toasts.push({ id, message, success });
      setTimeout(() => {
        this.toasts = this.toasts.filter(t => t.id !== id);
      }, 5000);
    },
  },
}
</script>
<template>
  <div class="content">
    <div class="container-fluid">
      <div class="toast-container">
        <div v-for="toast in toasts" :key="toast.id"
          class="toast show toast-item" :class="toast.success ? 'toast-success' : 'toast-error'">
          <span>{{ toast.success ? 'Success' : 'Error' }}: </span>{{ toast.message }}
        </div>
      </div>

      <h1 class="display-4 text-center mb-4">Settings</h1>

      <div class="settings-panel mx-auto">
        <div v-if="loading" class="text-center text-muted">Loading settings…</div>
        <form v-else @submit.prevent="saveSettings">
          <div class="p-3 border rounded settings-section">
            <h5 class="d-flex align-items-center gap-2"><SvgIcon name="gear" size="18" /> Age restriction</h5>
            <p class="text-muted small mb-3">
              Filters extractors and content by maximum age rating. Applies to all downloads.
            </p>
            <div class="form-check form-switch mb-3">
              <input class="form-check-input" type="checkbox" role="switch" id="ageRestrictionEnabled"
                v-model="ageRestrictionEnabled">
              <label class="form-check-label" for="ageRestrictionEnabled">
                Restrict downloads by age rating
              </label>
            </div>
            <div v-if="ageRestrictionEnabled" class="mb-2">
              <label for="ageLimit" class="form-label">Maximum age rating</label>
              <input type="number" class="form-control" id="ageLimit" min="0" step="1"
                v-model="ageLimit" style="max-width: 10rem;">
            </div>
          </div>

          <div class="p-3 border rounded settings-section mt-3">
            <h5 class="d-flex align-items-center gap-2"><SvgIcon name="folder" size="18" /> Download folders</h5>
            <p class="text-muted small mb-3">
              Named subfolders you can pick as the destination when queueing a download, so
              it's already sorted where it belongs instead of needing to be moved afterward.
              Leave "Container path" blank to nest under the default output folder, or set it
              to a separately mounted container path (e.g. Unraid's <code>/concerts</code>) to
              download straight there instead.
            </p>
            <ul v-if="downloadFolders.length" class="list-group mb-3">
              <li v-for="(folder, index) in downloadFolders" :key="folder.name"
                class="list-group-item d-flex justify-content-between align-items-center">
                <span>
                  {{ folder.name }}
                  <span v-if="folder.path" class="text-muted small">&rarr; {{ folder.path }}</span>
                </span>
                <button type="button" class="btn btn-sm btn-outline-danger" @click="removeFolder(index)"
                  :aria-label="`Remove ${folder.name}`">
                  <SvgIcon name="trash" size="14" />
                </button>
              </li>
            </ul>
            <p v-else class="text-muted small mb-3">No folders configured yet - downloads go to the default output path.</p>
            <div class="d-flex flex-wrap gap-2">
              <input type="text" class="form-control" style="max-width: 12rem;" placeholder="e.g. Movies"
                v-model="newFolderName" @keydown.enter.prevent="addFolder" aria-label="New folder name">
              <input type="text" class="form-control" style="max-width: 16rem;"
                placeholder="Container path (optional, e.g. /concerts)" v-model="newFolderPath"
                @keydown.enter.prevent="addFolder" aria-label="Container path (optional)">
              <button type="button" class="btn btn-outline-secondary" @click="openBrowser">Browse&hellip;</button>
              <button type="button" class="btn btn-outline-secondary" @click="addFolder">Add</button>
            </div>
          </div>

          <div class="text-center mt-3">
            <button type="submit" class="btn btn-primary" :disabled="saving">
              {{ saving ? 'Saving…' : 'Save settings' }}
            </button>
          </div>
        </form>
      </div>
      <DirectoryBrowserModal ref="dirBrowser" @select="onFolderPathSelected" />
    </div>
  </div>
</template>

<style scoped>
.settings-panel {
  max-width: 40rem;
}
</style>
