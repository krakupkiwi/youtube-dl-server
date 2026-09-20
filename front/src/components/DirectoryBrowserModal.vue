<script>
import { Modal } from 'bootstrap'
import { getAPIUrl } from '../utils'
import SvgIcon from './SvgIcon.vue'

export default {
  components: { SvgIcon },
  emits: ['select'],
  data: () => ({
    modal: null,
    currentPath: '',
    parentPath: null,
    dirs: [],
    loading: false,
    error: '',
  }),
  mounted() {
    this.modal = new Modal(this.$refs.modalEl);
  },
  methods: {
    open(startPath) {
      this.modal.show();
      this.browse(startPath || '');
    },
    async browse(path) {
      this.loading = true;
      this.error = '';
      try {
        // No path -> let the server pick its own platform-correct default
        // root (e.g. Docker/Linux "/" vs. a Windows drive root), rather than
        // assuming "/" is always valid client-side.
        const query = path ? `?path=${encodeURIComponent(path)}` : '';
        const url = getAPIUrl(`api/browse-dirs${query}`, import.meta.env);
        const response = await fetch(url);
        const data = await response.json();
        if (!data.success) {
          this.error = data.message || 'Could not list that directory.';
          return;
        }
        this.currentPath = data.path;
        this.parentPath = data.parent;
        this.dirs = data.dirs;
      } catch (e) {
        this.error = e.message || 'Network error while browsing.';
      } finally {
        this.loading = false;
      }
    },
    goUp() {
      if (this.parentPath) this.browse(this.parentPath);
    },
    enter(dirName) {
      const sep = /[/\\]$/.test(this.currentPath) ? '' : '/';
      this.browse(this.currentPath + sep + dirName);
    },
    choose() {
      this.$emit('select', this.currentPath);
      this.modal.hide();
    },
  },
}
</script>

<template>
  <div class="modal fade" ref="modalEl" tabindex="-1" aria-hidden="true">
    <div class="modal-dialog">
      <div class="modal-content">
        <div class="modal-header">
          <h5 class="modal-title">Choose a folder</h5>
          <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>
        </div>
        <div class="modal-body">
          <div class="d-flex align-items-center gap-2 mb-2">
            <button type="button" class="btn btn-sm btn-outline-secondary" @click="goUp" :disabled="!parentPath || loading">
              &uarr; Up
            </button>
            <code class="text-truncate current-path">{{ currentPath }}</code>
          </div>
          <div v-if="loading" class="text-center text-muted py-3">Loading&hellip;</div>
          <div v-else-if="error" class="text-danger small">{{ error }}</div>
          <ul v-else-if="dirs.length" class="list-group browse-list">
            <li v-for="dir in dirs" :key="dir" class="list-group-item list-group-item-action"
              role="button" tabindex="0" @click="enter(dir)" @keydown.enter="enter(dir)">
              <SvgIcon name="folder" size="14" /> {{ dir }}
            </li>
          </ul>
          <p v-else class="text-muted small mb-0">No subfolders here.</p>
        </div>
        <div class="modal-footer">
          <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Cancel</button>
          <button type="button" class="btn btn-primary" @click="choose" :disabled="!currentPath || loading">
            Select this folder
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.current-path {
  flex: 1;
  min-width: 0;
}

.browse-list {
  max-height: 16rem;
  overflow-y: auto;
}
</style>
