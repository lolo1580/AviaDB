<script setup>
import { computed } from 'vue'
import { coverPhoto, photoUrl } from '../api'
import { classPath } from '../classes'
import { STATUS_BADGE, STATUS_LABEL, TYPE_BADGE, TYPE_LABEL, formatMoney } from '../labels'
import AppIcon from './layout/AppIcon.vue'

const props = defineProps({
  item: { type: Object, required: true },
  clickable: { type: Boolean, default: true },
})
defineEmits(['edit'])

const cover = computed(() => coverPhoto(props.item))
const classLabel = computed(() => classPath(props.item.class_id))
const specifics = computed(() => {
  const it = props.item
  if (it.item_type === 'DIECAST' && it.diecast) {
    return [it.diecast.scale, it.diecast.manufacturer].filter(Boolean).join(' · ')
  }
  if (it.item_type === 'PATCH' && it.patch) {
    return [it.patch.unit_squadron, it.patch.base].filter(Boolean).join(' · ')
  }
  return ''
})
</script>

<template>
  <article
    class="flex cursor-pointer items-center gap-3 rounded-xl border border-slate-200 bg-white p-3 shadow-sm transition hover:shadow-md sm:gap-4 dark:border-slate-800 dark:bg-slate-900"
    @click="$emit('edit', item)"
  >
    <button
      type="button"
      class="h-12 w-12 shrink-0 overflow-hidden rounded-lg bg-slate-100 dark:bg-slate-800"
      :aria-label="item.name"
      @click.stop="$emit('edit', item)"
    >
      <img v-if="cover" :src="photoUrl(cover.file_path, 480)" alt="" class="h-full w-full object-cover" />
      <span v-else class="grid h-full w-full place-items-center text-slate-300 dark:text-slate-600">
        <AppIcon name="collection" size="h-5 w-5" />
      </span>
    </button>

    <div class="min-w-0 flex-1">
      <div class="flex flex-wrap items-center gap-2">
        <button
          type="button"
          class="truncate text-sm font-semibold text-slate-900 hover:text-sky-700 dark:text-slate-100 dark:hover:text-sky-400"
          @click.stop="$emit('edit', item)"
        >
          {{ item.name }}
        </button>
        <span class="rounded px-1.5 py-0.5 text-xs font-semibold ring-1 ring-inset" :class="TYPE_BADGE[item.item_type]">
          {{ TYPE_LABEL[item.item_type] }}
        </span>
      </div>

      <div class="mt-0.5 flex flex-wrap items-center gap-x-3 gap-y-0.5 text-xs text-slate-500 dark:text-slate-400">
        <span v-if="item.country">{{ item.country }}</span>
        <span v-if="specifics">{{ specifics }}</span>
        <span v-if="classLabel" class="truncate text-sky-700 dark:text-sky-400">{{ classLabel }}</span>
        <span v-for="tag in item.tags.slice(0, 3)" :key="tag.id" class="truncate">{{ tag.name }}</span>
      </div>
    </div>

    <span
      class="hidden shrink-0 rounded px-2 py-0.5 text-xs font-medium ring-1 ring-inset sm:inline"
      :class="STATUS_BADGE[item.status]"
    >
      {{ STATUS_LABEL[item.status] }}
    </span>

    <span
      v-if="item.estimated_value != null"
      class="w-20 shrink-0 text-right text-sm font-semibold text-slate-700 sm:w-24 dark:text-slate-200"
    >
      {{ formatMoney(item.estimated_value, item.currency) }}
    </span>
  </article>
</template>
