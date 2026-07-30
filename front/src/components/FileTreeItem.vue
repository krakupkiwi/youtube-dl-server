<template>
    <tr :class="{ 'directory': item.directory }" @click="toggleDirectory" @keydown.enter="toggleDirectory"
      role="button" tabindex="0" :aria-expanded="isOpen"
      v-if="item.directory" style="cursor: pointer;">
      <td class="col-select" @click.stop>
        <input type="checkbox" :aria-label="`Select ${item.name}`" :checked="isSelected" @click.stop="$emit('toggle-select', fullPath)" />
      </td>
      <td class="col-action file-tree-actions">
        <a type="button">
          <SvgIcon :name="isOpen ? 'folder-open' : 'folder'" color="var(--bs-teal)" size="14" />
        </a>
        <a href="#" @click.stop.prevent="$emit('delete', item.name)">
          <SvgIcon name="trash" color="var(--bs-red)" size="14" />
        </a>
      </td>
      <td :style="{ paddingLeft: (depth * 1.5 + 0.75) + 'rem' }"><b>{{ depth > 0 ? '\u21b3 ' : ''}}{{ item.name }}</b></td>
      <td class="col-size"></td>
      <td class="col-date">{{ formatDate(item.modified) }}</td>
      <td class="col-date">{{ formatDate(item.created) }}</td>
    </tr>
    <template v-if="item.directory && isOpen">
      <tr v-if="loadingChildren">
        <td :colspan="6" class="text-center text-muted">Loading…</td>
      </tr>
      <FileTreeItem
        v-else
        v-for="child in orderedChildren"
        :key="child.name"
        :item="child"
        :depth="depth + 1"
        :parent-path="parentPath ? `${parentPath}/${item.name}` : item.name"
        :selected-paths="selectedPaths"
        :sort-by="sortBy"
        :sort-order="sortOrder"
        @delete="$emit('delete', parentPath ? `${parentPath}/${item.name}/${$event}` : `${item.name}/${$event}`)"
        @cut="$emit('cut', parentPath ? `${parentPath}/${item.name}/${$event}` : `${item.name}/${$event}`)"
        @toggle-select="$emit('toggle-select', $event)"
      />
    </template>
    <tr v-else-if="!item.directory">
      <td class="col-select">
        <input type="checkbox" :aria-label="`Select ${item.name}`" :checked="isSelected" @click.stop="$emit('toggle-select', fullPath)" />
      </td>
      <td class="col-action file-tree-actions">
        <a :href="`api/finished/${encodeURIComponent(fullPath)}`" download>
          <SvgIcon name="download" color="var(--bs-teal)" size="14" />
        </a>
        <a v-if="isMedia" href="#" @click.prevent="$emit('cut', item.name)" style="cursor: pointer;" title="Cut">
          <SvgIcon name="scissors" color="var(--bs-orange)" size="14" />
        </a>
        <a href="#" @click.prevent="$emit('delete', item.name)" style="cursor: pointer;">
          <SvgIcon name="trash" color="var(--bs-red)" size="14" />
        </a>
      </td>
      <td :style="{ paddingLeft: (depth * 1.5 + 0.75) + 'rem' }">{{ depth > 0 ? '\u21b3 ' : ''}}<a :href="`api/finished/${encodeURIComponent(fullPath)}`">{{ item.name }}</a></td>
      <td class="col-size">{{ prettySize(item.size) }}</td>
      <td class="col-date">{{ formatDate(item.modified) }}</td>
      <td class="col-date">{{ formatDate(item.created) }}</td>
    </tr>
</template>

<script>
import { orderBy } from 'lodash'
import { getAPIUrl } from '../utils'
import SvgIcon from './SvgIcon.vue'

export default {
  name: 'FileTreeItem',
  components: { SvgIcon },
  emits: ['delete', 'cut', 'toggle-select'],
  props: {
    item: Object,
    parentPath: String,
    depth: Number,
    selectedPaths: {
      type: Array,
      default: () => []
    },
    sortBy: String,
    sortOrder: String,
  },
  data() {
    return {
      isOpen: false,
      loadedChildren: null,
      loadingChildren: false,
    }
  },
  computed: {
    fullPath() {
      return this.parentPath ? `${this.parentPath}/${this.item.name}` : this.item.name
    },
    isSelected() {
      return this.selectedPaths.includes(this.fullPath)
    },
    orderedChildren() {
      const children = this.loadedChildren ?? this.item.children ?? [];
      return orderBy(children, this.sortBy, this.sortOrder);
    },
    isMedia() {
      const ext = this.item.name.split('.').pop().toLowerCase();
      return ['mp4', 'mkv', 'webm', 'avi', 'mov', 'flv', 'ts', 'm4v',
        'mp3', 'm4a', 'aac', 'ogg', 'opus', 'flac', 'wav'].includes(ext);
    }
  },
  methods: {
    async toggleDirectory() {
      if (!this.item.directory) return;
      if (!this.isOpen && this.item.children === null && this.loadedChildren === null) {
        this.loadingChildren = true;
        try {
          const url = getAPIUrl(`api/finished?path=${encodeURIComponent(this.fullPath)}`, import.meta.env);
          const response = await fetch(url);
          if (!response.ok) throw new Error(response.statusText);
          this.loadedChildren = await response.json();
        } catch (error) {
          console.error(error);
          this.loadedChildren = [];
        } finally {
          this.loadingChildren = false;
        }
      }
      this.isOpen = !this.isOpen;
    },
    formatDate(ts) {
      if (ts == null) return '';
      const d = new Date(ts * 1000);
      const pad = n => String(n).padStart(2, '0');
      return `${pad(d.getHours())}:${pad(d.getMinutes())} ${pad(d.getMonth() + 1)}/${pad(d.getDate())}`;
    },
    prettySize(size_b) {
      if (size_b == null) {
        return '';
      }
      var sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
      var i = 0;
      for (i = 0; i < sizes.length; i++) {
        if (size_b < 1024) {
          i++;
          break
        }
        size_b = size_b / 1024;
      }
      return Number((size_b).toFixed(2)) + ' ' + sizes[i - 1];
    },
  }
}
</script>
