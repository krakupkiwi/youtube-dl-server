<script setup>
import { getAPIUrl } from '../utils'
import SvgIcon from './SvgIcon.vue'
</script>
<script>
export default {
  data: () => ({
    ageRestrictionEnabled: false,
    ageLimit: 18,
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
          body: JSON.stringify({ age_limit }),
        });
        const result = await response.json();
        if (!result.success) {
          this.showToast(result.message || 'Could not save settings.', false);
        } else {
          this.showToast('Settings saved.', true);
        }
      } catch (error) {
        this.showToast(error.message || 'Network error while saving settings.', false);
      } finally {
        this.saving = false;
      }
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

          <div class="text-center mt-3">
            <button type="submit" class="btn btn-primary" :disabled="saving">
              {{ saving ? 'Saving…' : 'Save settings' }}
            </button>
          </div>
        </form>
      </div>
    </div>
  </div>
</template>

<style scoped>
.settings-panel {
  max-width: 40rem;
}
</style>
