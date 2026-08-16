<script setup lang="ts">
import { Highlighter, Image as ImageIcon, Lightbulb, Link2 } from "@lucide/vue";
import Highlight from "@tiptap/extension-highlight";
import { Mathematics, migrateMathStrings } from "@tiptap/extension-mathematics";
import "katex/dist/katex.min.css";
// TableKit already bundles tableRow/tableHeader/tableCell -- registering
// those separately makes TipTap warn about duplicate extension names.
import { TableKit } from "@tiptap/extension-table";
import { Color, TextStyle } from "@tiptap/extension-text-style";
import StarterKit from "@tiptap/starter-kit";
import { EditorContent, useEditor } from "@tiptap/vue-3";
import { onBeforeUnmount, ref, watch } from "vue";

import { uploadLessonContentImage } from "@/api/lessons";
import { CALLOUT_VARIANTS, Callout } from "@/components/richtext/extensions/callout";
import { IMAGE_SIZES, ContentImage, type ImageSize } from "@/components/richtext/extensions/contentImage";
import { GlossaryTerm } from "@/components/richtext/extensions/glossaryTerm";
import { hasMath, parseMath } from "@/utils/math";
import { parseRichContent, plainTextToDoc } from "@/utils/richContent";

const props = withDefaults(defineProps<{ modelValue: string; label?: string; minHeight?: string }>(), {
  minHeight: "12rem",
});
const emit = defineEmits<{ (e: "update:modelValue", value: string): void }>();

const TEXT_COLORS: { value: string; label: string; swatch: string }[] = [
  { value: "teal", label: "Бирюзовый", swatch: "rgb(13 148 136)" },
  { value: "blue", label: "Синий", swatch: "rgb(37 99 235)" },
  { value: "green", label: "Зелёный", swatch: "rgb(21 128 61)" },
  { value: "amber", label: "Оранжевый", swatch: "rgb(180 83 9)" },
  { value: "red", label: "Красный", swatch: "rgb(220 38 38)" },
  { value: "purple", label: "Фиолетовый", swatch: "rgb(126 34 206)" },
];

const uploadError = ref("");
const uploading = ref(false);
const fileInput = ref<HTMLInputElement | null>(null);
const glossaryDraft = ref("");
const glossaryOpen = ref(false);

/** Seeds the editor from whatever the field currently holds -- a rich
 * document, or legacy plain text that gets converted (glossary markup and
 * all) so opening an old lesson never loses anything. */
function initialContent(raw: string) {
  const parsed = parseRichContent(raw);
  if (parsed.kind === "rich") return parsed.doc;
  if (parsed.kind === "plain") return plainTextToDoc(parsed.text);
  return "";
}

const editor = useEditor({
  content: initialContent(props.modelValue),
  extensions: [
    StarterKit.configure({
      heading: { levels: [2, 3] },
      link: { openOnClick: false, HTMLAttributes: { rel: "noopener noreferrer nofollow", target: "_blank" } },
    }),
    TextStyle,
    Color,
    Highlight,
    TableKit.configure({ table: { resizable: false } }),
    // `trust: false` keeps teacher-authored LaTeX from emitting links or raw
    // HTML (e.g. \href); `throwOnError: false` shows a typo as red source
    // text instead of blowing up the whole document.
    Mathematics.configure({ katexOptions: { throwOnError: false, trust: false } }),
    ContentImage,
    Callout,
    GlossaryTerm,
  ],
  editorProps: {
    attributes: { class: "rich-content rich-editor-surface focus:outline-none" },
    handlePaste: (_view, event) => {
      const file = [...(event.clipboardData?.files ?? [])].find((f) => f.type.startsWith("image/"));
      if (!file) {
        // Let TipTap insert the text first, then turn any `$…$` it contains
        // into real math nodes. This is the common case: teachers paste
        // explanations from an AI assistant, which come dollar-delimited.
        queueMicrotask(runMathMigration);
        return false;
      }
      event.preventDefault();
      void insertImageFile(file);
      return true;
    },
    handleDrop: (_view, event) => {
      const file = [...((event as DragEvent).dataTransfer?.files ?? [])].find((f) => f.type.startsWith("image/"));
      if (!file) return false;
      event.preventDefault();
      void insertImageFile(file);
      return true;
    },
  },
  // Lessons written before maths existed hold raw `$…$` text; converting on
  // open means the teacher sees rendered formulas immediately and a plain
  // re-save fixes the stored document for good.
  onCreate: () => queueMicrotask(runMathMigration),
  onUpdate: ({ editor: instance }) => {
    emit("update:modelValue", JSON.stringify(instance.getJSON()));
  },
});

function runMathMigration() {
  const instance = editor.value;
  if (!instance || instance.isDestroyed) return;
  migrateMathStrings(instance);
  convertLeftoverMath(instance);
}

/**
 * Second pass over what TipTap's own migration leaves behind.
 *
 * TipTap deliberately skips bare numerics like `$1$` (guarding against prices
 * such as "$5"), but the student renderer does convert them -- see
 * utils/math.ts, which only accepts a *paired* delimiter with no adjacent
 * space. Without this pass the teacher would see `$1$` while the student saw
 * a rendered 1, which is exactly the WYSIWYG gap this editor exists to close.
 *
 * Replacements shift every position after them, so this re-scans after each
 * one instead of collecting a batch up front.
 */
function convertLeftoverMath(instance: NonNullable<typeof editor.value>) {
  for (let guard = 0; guard < 300; guard += 1) {
    // Collected into an array rather than a single mutable local: TypeScript
    // cannot see that the descendants callback assigns, and would narrow a
    // `let hit = null` to `never` after the call.
    const hits: { from: number; to: number; latex: string }[] = [];

    instance.state.doc.descendants((node, pos) => {
      if (hits.length) return false;
      if (!node.isText || !node.text || !hasMath(node.text)) return true;
      // Inside a code block the dollars are the literal point of the text.
      if (instance.state.doc.resolve(pos).parent.type.name === "codeBlock") return true;

      let offset = 0;
      for (const segment of parseMath(node.text)) {
        if (segment.type === "math") {
          hits.push({ from: pos + offset, to: pos + offset + segment.latex.length + 2, latex: segment.latex });
          return false;
        }
        offset += segment.value.length;
      }
      return true;
    });

    const hit = hits[0];
    if (!hit) return;
    instance
      .chain()
      .insertContentAt({ from: hit.from, to: hit.to }, { type: "inlineMath", attrs: { latex: hit.latex } })
      .run();
  }
}

// Only react to a value the parent changed behind our back (e.g. switching
// which lesson is being edited) -- echoing our own onUpdate back in would
// reset the cursor on every keystroke.
watch(
  () => props.modelValue,
  (value) => {
    const instance = editor.value;
    if (!instance) return;
    if (JSON.stringify(instance.getJSON()) === value) return;
    instance.commands.setContent(initialContent(value), { emitUpdate: false });
  },
);

onBeforeUnmount(() => editor.value?.destroy());

async function insertImageFile(file: File) {
  uploadError.value = "";
  uploading.value = true;
  try {
    const path = await uploadLessonContentImage(file);
    editor.value?.chain().focus().setImage({ src: path }).run();
  } catch {
    uploadError.value = "Не удалось загрузить изображение (jpg, png, webp, до 5 МБ).";
  } finally {
    uploading.value = false;
  }
}

function handleFilePick(event: Event) {
  const input = event.target as HTMLInputElement;
  const file = input.files?.[0];
  if (file) void insertImageFile(file);
  // Reset so picking the same file twice in a row still fires a change.
  input.value = "";
}

function setImageSize(size: ImageSize) {
  editor.value?.chain().focus().updateAttributes("image", { size }).run();
}

function promptLink() {
  const instance = editor.value;
  if (!instance) return;
  if (instance.isActive("link")) {
    instance.chain().focus().unsetLink().run();
    return;
  }
  const url = window.prompt("Ссылка (https://…)");
  if (!url) return;
  if (!/^(https?:|mailto:)/i.test(url.trim())) {
    uploadError.value = "Ссылка должна начинаться с https:// или mailto:";
    return;
  }
  instance.chain().focus().setLink({ href: url.trim() }).run();
}

function promptMath(display: boolean) {
  const instance = editor.value;
  if (!instance) return;
  const latex = window.prompt(
    display ? "Формула отдельной строкой (LaTeX), например: x = \\frac{-b}{2a}" : "Формула в строке (LaTeX), например: p^+",
  );
  if (!latex || !latex.trim()) return;
  const chain = instance.chain().focus();
  if (display) chain.insertBlockMath({ latex: latex.trim() }).run();
  else chain.insertInlineMath({ latex: latex.trim() }).run();
}

function openGlossary() {
  const instance = editor.value;
  if (!instance) return;
  if (instance.isActive("glossaryTerm")) {
    instance.chain().focus().unsetGlossaryTerm().run();
    return;
  }
  if (instance.state.selection.empty) {
    uploadError.value = "Сначала выделите слово, к которому нужна подсказка.";
    return;
  }
  uploadError.value = "";
  glossaryDraft.value = "";
  glossaryOpen.value = true;
}

function confirmGlossary() {
  const text = glossaryDraft.value.trim();
  if (!text) return;
  editor.value?.chain().focus().setGlossaryTerm(text).run();
  glossaryOpen.value = false;
  glossaryDraft.value = "";
}

const BTN = "flex h-8 min-w-8 items-center justify-center rounded px-1.5 text-xs font-medium transition-colors";
function toneFor(active: boolean) {
  return active ? "bg-moss text-moss-fg" : "text-ink-2 hover:bg-paper-2 hover:text-ink";
}
</script>

<template>
  <div>
    <span v-if="label" class="mb-1.5 block text-label text-ink-2">{{ label }}</span>

    <div class="overflow-hidden rounded-lg border border-line-strong bg-paper">
      <div v-if="editor" class="flex flex-wrap items-center gap-0.5 border-b border-line bg-paper-2 p-1.5">
        <button type="button" :class="[BTN, toneFor(editor.isActive('heading', { level: 2 }))]" title="Заголовок"
          @click="editor.chain().focus().toggleHeading({ level: 2 }).run()">H2</button>
        <button type="button" :class="[BTN, toneFor(editor.isActive('heading', { level: 3 }))]" title="Подзаголовок"
          @click="editor.chain().focus().toggleHeading({ level: 3 }).run()">H3</button>

        <span class="mx-1 h-5 w-px bg-line" />

        <button type="button" :class="[BTN, toneFor(editor.isActive('bold'))]" title="Жирный"
          @click="editor.chain().focus().toggleBold().run()"><b>Ж</b></button>
        <button type="button" :class="[BTN, toneFor(editor.isActive('italic'))]" title="Курсив"
          @click="editor.chain().focus().toggleItalic().run()"><i>К</i></button>
        <button type="button" :class="[BTN, toneFor(editor.isActive('underline'))]" title="Подчёркнутый"
          @click="editor.chain().focus().toggleUnderline().run()"><u>П</u></button>
        <button type="button" :class="[BTN, toneFor(editor.isActive('strike'))]" title="Зачёркнутый"
          @click="editor.chain().focus().toggleStrike().run()"><s>З</s></button>
        <button type="button" :class="[BTN, toneFor(editor.isActive('highlight'))]" title="Маркер"
          @click="editor.chain().focus().toggleHighlight().run()"><Highlighter :size="15" :stroke-width="1.8" /></button>

        <span class="mx-1 h-5 w-px bg-line" />

        <button v-for="color in TEXT_COLORS" :key="color.value" type="button"
          class="h-6 w-6 rounded-full border-2 border-line transition-transform hover:scale-110"
          :style="{ backgroundColor: color.swatch }" :title="color.label"
          @click="editor.chain().focus().setColor(color.value).run()" />
        <button type="button" :class="[BTN, toneFor(false)]" title="Убрать цвет"
          @click="editor.chain().focus().unsetColor().run()">⌫</button>

        <span class="mx-1 h-5 w-px bg-line" />

        <button type="button" :class="[BTN, toneFor(editor.isActive('bulletList'))]" title="Маркированный список"
          @click="editor.chain().focus().toggleBulletList().run()">•—</button>
        <button type="button" :class="[BTN, toneFor(editor.isActive('orderedList'))]" title="Нумерованный список"
          @click="editor.chain().focus().toggleOrderedList().run()">1.</button>
        <button type="button" :class="[BTN, toneFor(editor.isActive('blockquote'))]" title="Цитата"
          @click="editor.chain().focus().toggleBlockquote().run()">❝</button>
        <button type="button" :class="[BTN, toneFor(editor.isActive('codeBlock'))]" title="Формула или код"
          @click="editor.chain().focus().toggleCodeBlock().run()">{ }</button>
        <button type="button" :class="[BTN, toneFor(false)]" title="Разделитель"
          @click="editor.chain().focus().setHorizontalRule().run()">—</button>

        <span class="mx-1 h-5 w-px bg-line" />

        <button v-for="variant in CALLOUT_VARIANTS" :key="variant.value" type="button"
          :class="[BTN, toneFor(editor.isActive('callout', { variant: variant.value }))]"
          :title="`Врезка: ${variant.label}`" @click="editor.chain().focus().toggleCallout(variant.value).run()">
          {{ variant.label }}
        </button>

        <span class="mx-1 h-5 w-px bg-line" />

        <button type="button" :class="[BTN, toneFor(editor.isActive('link'))]" title="Ссылка" @click="promptLink">
          <Link2 :size="15" :stroke-width="1.8" />
        </button>
        <button type="button" :class="[BTN, toneFor(false)]" title="Вставить изображение" :disabled="uploading"
          @click="fileInput?.click()">
          <span v-if="uploading">…</span>
          <ImageIcon v-else :size="15" :stroke-width="1.8" />
        </button>
        <button type="button" :class="[BTN, toneFor(false)]" title="Вставить таблицу"
          @click="editor.chain().focus().insertTable({ rows: 3, cols: 3, withHeaderRow: true }).run()">⊞</button>
        <button type="button" :class="[BTN, toneFor(editor.isActive('inlineMath'))]"
          title="Формула в строке (LaTeX)" @click="promptMath(false)">√x</button>
        <button type="button" :class="[BTN, toneFor(editor.isActive('blockMath'))]"
          title="Формула отдельной строкой (LaTeX)" @click="promptMath(true)">∑</button>
        <button type="button" :class="[BTN, toneFor(editor.isActive('glossaryTerm'))]"
          title="Подсказка к термину (выделите слово)" @click="openGlossary">
          <Lightbulb :size="15" :stroke-width="1.8" />
        </button>

        <span class="mx-1 h-5 w-px bg-line" />

        <button type="button" :class="[BTN, toneFor(false)]" title="Отменить" :disabled="!editor.can().undo()"
          @click="editor.chain().focus().undo().run()">↶</button>
        <button type="button" :class="[BTN, toneFor(false)]" title="Повторить" :disabled="!editor.can().redo()"
          @click="editor.chain().focus().redo().run()">↷</button>
      </div>

      <!-- Contextual rows: only shown when the caret is actually inside that
           kind of node, so the toolbar above stays the same size. -->
      <div v-if="editor?.isActive('image')" class="flex flex-wrap items-center gap-1 border-b border-line bg-paper-2 px-1.5 py-1">
        <span class="px-1 text-xs text-ink-3">Размер изображения:</span>
        <button v-for="size in IMAGE_SIZES" :key="size.value" type="button"
          :class="[BTN, toneFor(editor.isActive('image', { size: size.value }))]" @click="setImageSize(size.value)">
          {{ size.label }}
        </button>
      </div>

      <div v-if="editor?.isActive('table')" class="flex flex-wrap items-center gap-1 border-b border-line bg-paper-2 px-1.5 py-1">
        <span class="px-1 text-xs text-ink-3">Таблица:</span>
        <button type="button" :class="[BTN, toneFor(false)]" @click="editor.chain().focus().addRowAfter().run()">+ строка</button>
        <button type="button" :class="[BTN, toneFor(false)]" @click="editor.chain().focus().addColumnAfter().run()">+ столбец</button>
        <button type="button" :class="[BTN, toneFor(false)]" @click="editor.chain().focus().deleteRow().run()">− строка</button>
        <button type="button" :class="[BTN, toneFor(false)]" @click="editor.chain().focus().deleteColumn().run()">− столбец</button>
        <button type="button" :class="[BTN, toneFor(false)]" @click="editor.chain().focus().deleteTable().run()">Удалить</button>
      </div>

      <div v-if="glossaryOpen" class="space-y-2 border-b border-line bg-paper-2 p-3">
        <p class="text-xs text-ink-2">Объяснение для выделенного термина:</p>
        <textarea v-model="glossaryDraft" rows="2" class="input text-sm" placeholder="Понятное объяснение…" />
        <div class="flex gap-2">
          <button type="button" class="btn-primary px-3 py-1.5 text-xs" :disabled="!glossaryDraft.trim()"
            @click="confirmGlossary">Добавить</button>
          <button type="button" class="btn-ghost px-3 py-1.5 text-xs" @click="glossaryOpen = false">Отмена</button>
        </div>
      </div>

      <EditorContent :editor="editor" class="px-3.5 py-3" :style="{ minHeight }" />
    </div>

    <input ref="fileInput" type="file" accept="image/jpeg,image/png,image/webp" class="hidden" @change="handleFilePick" />
    <p v-if="uploadError" class="mt-1 text-caption text-clay">{{ uploadError }}</p>
    <p class="mt-1 text-caption text-ink-3">
      Изображение можно вставить перетаскиванием или из буфера обмена.
    </p>
  </div>
</template>
