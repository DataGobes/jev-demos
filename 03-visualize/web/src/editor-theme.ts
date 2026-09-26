/**
 * Dark theme + SQL highlighting for the editor.
 *
 * CodeMirror's `basicSetup` ships `defaultHighlightStyle`, which is tuned for a
 * light page: keywords come out dark purple (#708) and strings dark red (#a11).
 * Both sit near the bottom of the contrast range on `--panel`, which is exactly
 * where the demo needs to be readable from the back of a room.
 *
 * Every colour below was checked for WCAG contrast against the editor
 * background; all clear 4.5:1.
 */

import { HighlightStyle, syntaxHighlighting } from "@codemirror/language";
import { EditorView } from "@codemirror/view";
import { tags as t } from "@lezer/highlight";

const BG = "#171a21"; // --panel
const TEXT = "#e6e8ee"; // --text
const MUTED = "#8b93a7"; // --muted
const LINE = "#262b36"; // --line
const ACCENT = "#ff7a3d"; // --accent

const KEYWORD = "#7fb0ff"; // 7.9:1
const BUILTIN = "#5ccfe6"; // 9.6:1
const STRING = "#ffcb6b"; // 11.6:1
const NUMBER = "#f2a0c0"; // 8.8:1
const PUNCT = "#9aa4bd"; // 7.0:1
const COMMENT = "#8891a6"; // 5.3:1

export const editorTheme = EditorView.theme({
  "&": { color: TEXT, backgroundColor: BG },
  ".cm-content": { fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace", fontSize: "14px", lineHeight: "1.6", caretColor: ACCENT, padding: "8px 0" },
  ".cm-cursor, .cm-dropCursor": { borderLeftColor: ACCENT, borderLeftWidth: "2px" },
  "&.cm-focused .cm-selectionBackground, .cm-selectionBackground, .cm-content ::selection": { backgroundColor: "#2b3550" },
  ".cm-activeLine": { backgroundColor: "#ffffff0a" },
  ".cm-gutters": { backgroundColor: BG, color: "#5c6478", border: "none" },
  ".cm-activeLineGutter": { backgroundColor: "#ffffff0a", color: MUTED },
  ".cm-selectionMatch": { backgroundColor: "#ffffff14" },
  ".cm-matchingBracket, &.cm-focused .cm-matchingBracket": { backgroundColor: "#ffffff1a", outline: `1px solid ${LINE}` },
}, { dark: true });

/**
 * Ordinary SQL reads cool; the `VISUALIZE` clause reads warm. The keyword itself
 * is the app accent (see `.cm-visualize`) and the intent string beside it is
 * amber, so the clause the demo is about reads as one warm unit against the
 * blue-and-white SQL around it.
 */
export const sqlHighlight = syntaxHighlighting(HighlightStyle.define([
  { tag: [t.keyword, t.operatorKeyword, t.controlKeyword, t.definitionKeyword, t.modifier], color: KEYWORD },
  { tag: [t.string, t.special(t.string), t.character], color: STRING },
  { tag: [t.number, t.bool, t.null, t.integer, t.float], color: NUMBER },
  { tag: [t.typeName, t.standard(t.name), t.function(t.variableName)], color: BUILTIN },
  { tag: [t.operator, t.punctuation, t.separator, t.bracket, t.paren], color: PUNCT },
  // Identifiers are deliberately left uncoloured so they inherit `.cm-content`'s
  // colour. Naming them here would paint a token span *inside* the `VISUALIZE`
  // mark decoration, and the inner span's own colour beats the outer mark's -
  // which silently turns the accent-coloured keyword white.
  { tag: [t.comment, t.lineComment, t.blockComment], color: COMMENT, fontStyle: "italic" },
  { tag: t.invalid, color: "#ff8080" },
]));
