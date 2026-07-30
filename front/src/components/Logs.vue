<script setup>
import { orderBy, capitalize } from 'lodash'
import { Modal } from 'bootstrap'
import { getAPIUrl, saveConfig, getConfig } from '../utils';
</script>
<script>
export default {
  data: () => ({
    logs: [],
    showLogDetails: true,
    eventSource: null,
    statusToTrClass: {
      Pending: 'badge bg-secondary',
      Failed: 'badge bg-danger',
      Aborted: 'badge bg-warning',
      Running: 'badge bg-info',
      Completed: 'badge bg-success'
    },
    sortBy: 'last_update',
    sortOrder: 'desc',
    currentLogDetailsModal: null,
    currentLogDetailId: null,
    status: null,
    selectedIds: [],
  }),
  watch: {
    '$route'() {
      this.status = this.$route.query.status;
      this.connectStream();
    },
    logs() {
      const ids = new Set(this.logs.map(log => log.id));
      this.selectedIds = this.selectedIds.filter(id => ids.has(id));
    },
  },
  mounted() {
    this.currentLogDetailsModal = new Modal('#currentLogDetailsModal');
    this.showLogDetails = getConfig('showLogDetails', 'true') === 'true';
    this.status = this.$route.query.status;
    this.connectStream();
  },
  unmounted() {
    this.disconnectStream();
  },
  computed: {
    getLogById: function () {
      return this.logs.find(log => log.id === this.currentLogDetailId);
    },
    orderedLogs: function () {
      if (this.sortBy === 'last_update') {
        return orderBy(this.logs, e => {
          return new Date(e.last_update)
        }, this.sortOrder)
      }
      return orderBy(this.logs, this.sortBy, this.sortOrder)
    },
    allSelected() {
      return this.orderedLogs.length > 0 && this.orderedLogs.every(log => this.selectedIds.includes(log.id));
    },
  },
  methods: {
    toggleSort(field) {
      if (this.sortBy === field) {
        this.sortOrder = this.sortOrder === 'asc' ? 'desc' : 'asc';
      } else {
        this.sortBy = field;
        this.sortOrder = 'desc';
      }
    },
    getFormatBadgeClass(format) {
      return format?.startsWith('profile/') ? 'badge bg-warning me-1' : 'badge bg-success me-1'
    },
    toggleSelected(jobId) {
      const idx = this.selectedIds.indexOf(jobId);
      if (idx === -1) {
        this.selectedIds.push(jobId);
      } else {
        this.selectedIds.splice(idx, 1);
      }
    },
    toggleSelectAll() {
      if (this.allSelected) {
        this.selectedIds = [];
      } else {
        this.selectedIds = this.orderedLogs.map(log => log.id);
      }
    },
    async bulkRetry() {
      await Promise.allSettled(this.selectedIds.map(id =>
        fetch(getAPIUrl(`api/jobs/${id}/retry`, import.meta.env), { method: 'POST' })
      ));
      this.selectedIds = [];
      this.fetchLogs();
    },
    async bulkDelete() {
      await Promise.allSettled(this.selectedIds.map(id =>
        fetch(getAPIUrl(`api/jobs/${id}`, import.meta.env), { method: 'DELETE' })
      ));
      this.selectedIds = [];
      this.fetchLogs();
    },
    showCurrentLogDetails(logId) {
      this.currentLogDetailId = logId
      this.currentLogDetailsModal.show();
    },
    abortDownload(job_id) {
      const url = getAPIUrl(`api/jobs/${job_id}/stop`, import.meta.env);
      fetch(url, {
        method: 'POST'
      })
      this.fetchLogs()
    },
    retryDownload(job_id) {
      const apiurl = getAPIUrl(`api/jobs/${job_id}/retry`, import.meta.env);
      fetch(apiurl, {
        method: 'POST'
      }).then(() => {
        this.fetchLogs();
      })
    },
    deleteLog(job_id) {
      const apiurl = getAPIUrl(`api/jobs/${job_id}`, import.meta.env);
      fetch(apiurl, {
        method: 'DELETE'
      }).then(() => {
        this.fetchLogs();
      })
    },
    purgeLogs() {
      const url = getAPIUrl(`api/downloads`, import.meta.env);
      fetch(url, {
        method: 'DELETE',
        headers: {
          'Content-Type': 'application/json'
        }
      })
      this.fetchLogs()
    },
    async fetchLogs() {
      const url = getAPIUrl(`api/downloads?${this.status ? 'status=' + this.status : ''}`, import.meta.env);
      try {
        const response = await fetch(url);
        if (!response.ok) throw new Error(response.statusText);
        this.logs = await response.json();
      } catch (error) {
        console.error(error);
      }
    },
    connectStream() {
      this.disconnectStream();
      const url = getAPIUrl(`api/downloads/stream?${this.status ? 'status=' + this.status : ''}`, import.meta.env);
      this.eventSource = new EventSource(url);
      this.eventSource.onmessage = (event) => {
        this.logs = JSON.parse(event.data);
      };
      this.eventSource.onerror = () => {
        // EventSource retries the connection on its own; nothing to do here.
        console.error('Logs stream connection error, retrying...');
      };
    },
    disconnectStream() {
      if (this.eventSource) {
        this.eventSource.close();
        this.eventSource = null;
      }
    },
  }
}
</script>
<template>
  <div class="content">
    <div class="container-fluid d-flex flex-column text-center">
      <div class="container-fluid flex-grow-1">
        <h1 class="display-4">Jobs History</h1>
        <div class="d-flex justify-content-center gap-2 flex-wrap mb-3">
          <div class="btn-group" role="toolbar">
            <button v-if="showLogDetails" class="btn btn-outline-secondary col-hide-mobile"
              @click="showLogDetails = false; saveConfig('showLogDetails', false)">Hide logs</button>
            <button v-else class="btn btn-outline-secondary col-hide-mobile"
              @click="showLogDetails = true; saveConfig('showLogDetails', true)">Show logs</button>
            <button class="btn btn-outline-secondary" @click="fetchLogs">Refresh</button>
            <button class="btn btn-outline-danger" @click="purgeLogs">Purge</button>
          </div>
          <div class="dropdown">
            <a class="btn btn-outline-secondary dropdown-toggle" href="#" role="button" id="statusFilterDropDown" data-bs-toggle="dropdown" aria-expanded="false">
              Status {{ ['COMPLETED', 'FAILED', 'PENDING', 'RUNNING', 'ABORTED'].includes(status) ? `(${capitalize(status)})` : '(All)' }}
            </a>
            <ul class="dropdown-menu" aria-labelledby="statusFilterDropDown">
              <li><router-link class="dropdown-item" to="/logs">All</router-link></li>
              <li><router-link class="dropdown-item" to="/logs?status=COMPLETED">Completed</router-link></li>
              <li><router-link class="dropdown-item" to="/logs?status=FAILED">Failed</router-link></li>
              <li><router-link class="dropdown-item" to="/logs?status=PENDING">Pending</router-link></li>
              <li><router-link class="dropdown-item" to="/logs?status=RUNNING">Running</router-link></li>
              <li><router-link class="dropdown-item" to="/logs?status=ABORTED">Aborted</router-link></li>
            </ul>
          </div>
        </div>
        <div v-if="selectedIds.length" class="d-flex justify-content-center align-items-center gap-2 mb-3">
          <span class="text-muted">{{ selectedIds.length }} selected</span>
          <button class="btn btn-sm btn-outline-primary" @click="bulkRetry">Retry selected</button>
          <button class="btn btn-sm btn-outline-danger" @click="bulkDelete">Delete selected</button>
        </div>
        <div class="table-responsive">
          <table class="table table-striped table-hover">
            <thead>
              <tr>
                <th class="col-select">
                  <input type="checkbox" aria-label="Select all jobs" :checked="allSelected" @click.stop="toggleSelectAll" />
                </th>
                <th class="sortable-header col-hide-mobile" role="button" tabindex="0"
                  :aria-sort="sortBy === 'last_update' ? (sortOrder === 'asc' ? 'ascending' : 'descending') : 'none'"
                  @click="toggleSort('last_update')" @keydown.enter="toggleSort('last_update')" @keydown.space.prevent="toggleSort('last_update')">
                  Last update
                  <svg v-if="sortBy === 'last_update'" class="sort-chevron" :class="{ flipped: sortOrder === 'asc' }" xmlns="http://www.w3.org/2000/svg" width="12" height="12" fill="currentColor" viewBox="0 0 16 16">
                    <path d="M7.247 11.14 2.451 5.658C1.885 5.013 2.345 4 3.204 4h9.592a1 1 0 0 1 .753 1.659l-4.796 5.48a1 1 0 0 1-1.506 0z"/>
                  </svg>
                </th>
                <th class="sortable-header" role="button" tabindex="0"
                  :aria-sort="sortBy === 'name' ? (sortOrder === 'asc' ? 'ascending' : 'descending') : 'none'"
                  @click="toggleSort('name')" @keydown.enter="toggleSort('name')" @keydown.space.prevent="toggleSort('name')">
                  Name
                  <svg v-if="sortBy === 'name'" class="sort-chevron" :class="{ flipped: sortOrder === 'asc' }" xmlns="http://www.w3.org/2000/svg" width="12" height="12" fill="currentColor" viewBox="0 0 16 16">
                    <path d="M7.247 11.14 2.451 5.658C1.885 5.013 2.345 4 3.204 4h9.592a1 1 0 0 1 .753 1.659l-4.796 5.48a1 1 0 0 1-1.506 0z"/>
                  </svg>
                </th>
                <th class="sortable-header" role="button" tabindex="0"
                  :aria-sort="sortBy === 'format' ? (sortOrder === 'asc' ? 'ascending' : 'descending') : 'none'"
                  @click="toggleSort('format')" @keydown.enter="toggleSort('format')" @keydown.space.prevent="toggleSort('format')">
                  Format
                  <svg v-if="sortBy === 'format'" class="sort-chevron" :class="{ flipped: sortOrder === 'asc' }" xmlns="http://www.w3.org/2000/svg" width="12" height="12" fill="currentColor" viewBox="0 0 16 16">
                    <path d="M7.247 11.14 2.451 5.658C1.885 5.013 2.345 4 3.204 4h9.592a1 1 0 0 1 .753 1.659l-4.796 5.48a1 1 0 0 1-1.506 0z"/>
                  </svg>
                </th>
                <th class="sortable-header" role="button" tabindex="0"
                  :aria-sort="sortBy === 'status' ? (sortOrder === 'asc' ? 'ascending' : 'descending') : 'none'"
                  @click="toggleSort('status')" @keydown.enter="toggleSort('status')" @keydown.space.prevent="toggleSort('status')">
                  Status
                  <svg v-if="sortBy === 'status'" class="sort-chevron" :class="{ flipped: sortOrder === 'asc' }" xmlns="http://www.w3.org/2000/svg" width="12" height="12" fill="currentColor" viewBox="0 0 16 16">
                    <path d="M7.247 11.14 2.451 5.658C1.885 5.013 2.345 4 3.204 4h9.592a1 1 0 0 1 .753 1.659l-4.796 5.48a1 1 0 0 1-1.506 0z"/>
                  </svg>
                </th>
                <th class="col-hide-mobile" v-if="showLogDetails">Log</th>
              </tr>
            </thead>
            <tbody id="job_logs">
              <tr v-if="logs.length === 0">
                <td :colspan="showLogDetails ? 6 : 5">No {{ status == null ? '' : status.toLowerCase() + ' ' }}jobs found</td>
              </tr>
              <tr @click="showCurrentLogDetails(log.id)" @keydown.enter="showCurrentLogDetails(log.id)"
                role="button" tabindex="0"
                v-for="log in orderedLogs" :key="log.id" style="cursor: pointer;">
                <td @click.stop>
                  <input type="checkbox" :aria-label="`Select job ${log.name}`" :checked="selectedIds.includes(log.id)" @click.stop="toggleSelected(log.id)" />
                </td>
                <td class="col-hide-mobile">{{ log.last_update }}</td>
                <td class="col-name">{{ log.name }}</td>
                <td><span v-for='fmt in log.format?.split(",")' :class=getFormatBadgeClass(fmt)>{{ fmt }}</span></td>
                <td v-if="log.status == 'Failed' && log.extra_params?.not_yet_available">
                  <span class="badge bg-secondary status-action" @click.stop="retryDownload(log.id)"
                    title="yt-dlp reported this video isn't available yet (scheduled/upcoming). It will be retried automatically.">
                    Not available yet / Retry
                  </span>
                </td>
                <td v-else-if="log.status == 'Failed' || log.status == 'Aborted'">
                  <span :class=statusToTrClass[log.status] class="status-action" @click.stop="retryDownload(log.id)">
                    {{ log.status }} / Retry
                  </span>
                </td>
                <td v-else-if="log.status == 'Running' || log.status == 'Pending'">
                  <span :class=statusToTrClass[log.status] class="status-action" @click.stop="abortDownload(log.id)">
                    {{ log.status }} &times;
                  </span>
                </td>
                <td v-else>
                  <span :class=statusToTrClass[log.status]>
                    {{ log.status }}
                  </span>
                </td>
                <td class="text-start col-hide-mobile" v-if="showLogDetails">{{ log.log }}</td>
              </tr>
            </tbody>
          </table>
        </div>

        <div class="modal fade" id="currentLogDetailsModal" tabindex="-1" aria-hidden="true">
          <div class="modal-dialog modal-xl" id='currentLogDetailDialog' style="text-align: left">
            <div class="modal-content">
              <div class="modal-header">
                <span :class=statusToTrClass[getLogById?.status]>{{ getLogById?.status }}</span>&nbsp;
                <h1 class="modal-title fs-5" id="currentLogDetailId">{{ getLogById?.name || '' }}</h1>
                <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>
              </div>
              <div class="modal-body" id="currentLogDetailContent">
                <pre v-if="currentLogDetailId" class="log-output">{{ getLogById?.log }}</pre>
                <div v-else class="spinner-border" role="status">
                  <span class="visually-hidden">Loading...</span>
                </div>
              </div>
              <div class="modal-footer">
                <div v-if="getLogById?.status == 'Failed' || getLogById?.status == 'Aborted'">
                  <button class="btn btn-primary" role="button" aria-label="Retry" data-bs-dismiss="modal"
                    @click="retryDownload(getLogById?.id)">Retry</button>
                </div>
                <div v-else-if="getLogById?.status == 'Running' || getLogById?.status == 'Pending'">
                  <button class="btn btn-primary" role="button" aria-label="Abort" data-bs-dismiss="modal"
                    @click="abortDownload(getLogById?.id)">Abort</button>
                </div>
                <button type="button" class="btn btn-danger" data-bs-dismiss="modal" @click="deleteLog(getLogById?.id)">Delete log</button>
                <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Close</button>
              </div>
            </div>
          </div>
        </div>

      </div>
    </div>
  </div>
</template>
