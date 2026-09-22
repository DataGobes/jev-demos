import { sql } from "@codemirror/lang-sql";
import { EditorState } from "@codemirror/state";
import { Decoration, EditorView, MatchDecorator, ViewPlugin, keymap, type DecorationSet, type ViewUpdate } from "@codemirror/view";
import { basicSetup } from "codemirror";
import { editorTheme, sqlHighlight } from "./editor-theme";
import { useEffect, useRef } from "react";

const matcher = new MatchDecorator({ regexp: /\bVISUALIZE\b/gi, decoration: Decoration.mark({ class: "cm-visualize" }) });
const visualizeKeyword = ViewPlugin.fromClass(class {
  decorations: DecorationSet;
  constructor(view: EditorView) { this.decorations = matcher.createDeco(view); }
  update(u: ViewUpdate) { this.decorations = matcher.updateDeco(u, this.decorations); }
}, { decorations: (v) => v.decorations });

export function Editor({ value, onChange, onRun }: { value: string; onChange: (v: string) => void; onRun: () => void }) {
  const host = useRef<HTMLDivElement>(null);
  const view = useRef<EditorView | null>(null);
  const run = useRef(onRun); run.current = onRun;
  const change = useRef(onChange); change.current = onChange;

  useEffect(() => {
    view.current = new EditorView({ parent: host.current!, state: EditorState.create({ doc: value, extensions: [
      keymap.of([{ key: "Mod-Enter", run: () => { run.current(); return true; } }]),
      basicSetup, sql(), visualizeKeyword, editorTheme, sqlHighlight,
      // The VISUALIZE clause is the point of the demo, so no line may ever be
      // clipped - full width fixes today's overflow, wrapping keeps it fixed on
      // a narrower window or a projector.
      EditorView.lineWrapping,
      EditorView.updateListener.of((u) => { if (u.docChanged) change.current(u.state.doc.toString()); }),
    ] }) });
    return () => view.current?.destroy();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const v = view.current;
    if (v && v.state.doc.toString() !== value) v.dispatch({ changes: { from: 0, to: v.state.doc.length, insert: value } });
  }, [value]);

  return <div ref={host} className="editor" />;
}
