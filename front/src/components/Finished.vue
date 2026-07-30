<script setup>
import { orderBy } from 'lodash'
import { Modal } from 'bootstrap'
import { getAPIUrl } from '../utils'
import FileTreeItem from './FileTreeItem.vue'
import CutModal from './CutModal.vue'
import SvgIcon from './SvgIcon.vue'
</script>
<script>
export default {
  data: () => ({
    finished: [],
    sortBy: 'created',
    sortOrder: 'desc',
    toasts: [],
    pendingDeleteFile: null,
  }),
  mounted() {
    this.fetchFinished();
  },
  computed: {
    fileTreeOrdered() {
      return this.buildFileTree(this.finished)
    },
  },

  methods: {
    cutFinishedFile(file_name) {
      this.$refs.cutModal.open(file_name);
    },
    onCutQueued(output) {
      this.showToast(`Cut queued as ${output} — check the Logs page for progress.`, true);
    },
    deleteFinishedFile(file_name) {
      this.pendingDeleteFile = file_name;
      const modalEl = document.getElementById('deleteConfirmModal');
      modalEl.addEventListener('shown.bs.modal', () => {
        this.$refs.deleteBtn.focus();
      }, { once: true });
      new Modal(modalEl).show();
    },
    async confirmDelete() {
      const url = getAPIUrl(`api/finished/${encodeURIComponent(this.pendingDeleteFile)}`);
      this.pendingDeleteFile = null;
      try {
        const response = await fetch(url, {
          method: 'DELETE',
          headers: {
            'Content-Type': 'application/json'
          }
        });
        const result = await response.json();
        if (!result.success) {
          this.showToast(result.message || 'Could not delete the file.', false);
        } else {
          this.showToast(result.message || 'File deleted successfully.', true);
        }
      } catch (error) {
        this.showToast(error.message || 'Network error while deleting file.', false);
      }
      this.fetchFinished()
    },
    showToast(message, success = true) {
      const id = Date.now() + Math.random();
      this.toasts.push({ id, message, success });
      setTimeout(() => {
        this.toasts = this.toasts.filter(t => t.id !== id);
      }, 5000);
    },
    async fetchFinished() {
      const url = getAPIUrl(`api/finished`);
      try {
        const response = await fetch(url);
        if (!response.ok) throw new Error(response.statusText);
        this.finished = await response.json();
      } catch (error) {
        this.showToast(error.message || 'Could not load the finished files list.', false);
      }
    },
    order(items) {
      return orderBy(items, this.sortBy, this.sortOrder)
    },
    buildFileTree(items, parentPath = '') {
      const sortedItems = this.order(items);
      return sortedItems.map(item => {
        if (item.directory) {
          return {
            ...item,
            children: this.buildFileTree(item.children, `${parentPath}${item.name}/`)
          }
        }
        return item
      });
    },
    setSort(field) {
      if (this.sortBy === field) {
        this.sortOrder = this.sortOrder === 'asc' ? 'desc' : 'asc';
      } else {
        this.sortBy = field;
        this.sortOrder = field === 'name' ? 'asc' : 'desc';
      }
    },
  }
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

      <div class="row align-items-center mb-2">
        <h1 class="display-4 text-center col">Finished Files</h1>
        <div class="col-auto">
          <button class="btn btn-secondary" @click="fetchFinished" title="Refresh"><SvgIcon name="refresh" /></button>
        </div>
      </div>
      <div class="table-responsive">
        <table class="table file-tree-table text-left">
          <thead>
            <tr>
              <th class="col-action">Action</th>
              <th class="sortable-header" role="button" tabindex="0"
                :aria-sort="sortBy === 'name' ? (sortOrder === 'asc' ? 'ascending' : 'descending') : 'none'"
                @click="setSort('name')" @keydown.enter="setSort('name')" @keydown.space.prevent="setSort('name')">Name
                <span v-if="sortBy === 'name'" class="sort-chevron" :class="{ flipped: sortOrder === 'asc' }">▾</span>
              </th>
              <th class="col-size sortable-header" role="button" tabindex="0"
                :aria-sort="sortBy === 'size' ? (sortOrder === 'asc' ? 'ascending' : 'descending') : 'none'"
                @click="setSort('size')" @keydown.enter="setSort('size')" @keydown.space.prevent="setSort('size')">Size
                <span v-if="sortBy === 'size'" class="sort-chevron" :class="{ flipped: sortOrder === 'asc' }">▾</span>
              </th>
              <th class="col-date sortable-header" role="button" tabindex="0"
                :aria-sort="sortBy === 'modified' ? (sortOrder === 'asc' ? 'ascending' : 'descending') : 'none'"
                @click="setSort('modified')" @keydown.enter="setSort('modified')" @keydown.space.prevent="setSort('modified')">Modified
                <span v-if="sortBy === 'modified'" class="sort-chevron" :class="{ flipped: sortOrder === 'asc' }">▾</span>
              </th>
              <th class="col-date sortable-header" role="button" tabindex="0"
                :aria-sort="sortBy === 'created' ? (sortOrder === 'asc' ? 'ascending' : 'descending') : 'none'"
                @click="setSort('created')" @keydown.enter="setSort('created')" @keydown.space.prevent="setSort('created')">Downloaded
                <span v-if="sortBy === 'created'" class="sort-chevron" :class="{ flipped: sortOrder === 'asc' }">▾</span>
              </th>
            </tr>
          </thead>

          <tbody v-if="fileTreeOrdered.length > 0">
            <FileTreeItem v-for="item in fileTreeOrdered" :key="item.name" :item="item" :depth="0"
              @delete="deleteFinishedFile" @cut="cutFinishedFile" />
          </tbody>
          <tbody v-else>
            <tr>
              <td colspan="5" class="text-center text-muted" style="padding: 2rem;">No finished files found.</td>
            </tr>
          </tbody>
        </table>
      </div>
      <CutModal ref="cutModal" @queued="onCutQueued" />
      <div class="modal fade" id="deleteConfirmModal" tabindex="-1" aria-hidden="true">
        <div class="modal-dialog">
          <div class="modal-content">
            <div class="modal-header">
              <h5 class="modal-title">Delete file</h5>
              <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
            </div>
            <div class="modal-body">
              Are you sure you want to delete <strong>{{ pendingDeleteFile }}</strong>?
            </div>
            <div class="modal-footer">
              <button class="btn btn-secondary" data-bs-dismiss="modal">Cancel</button>
              <button ref="deleteBtn" class="btn btn-danger" data-bs-dismiss="modal" @click="confirmDelete">Delete</button>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
