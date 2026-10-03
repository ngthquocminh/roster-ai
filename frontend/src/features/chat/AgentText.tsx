import { Fragment, type ReactNode } from "react";

/**
 * Renders an agent answer with the small subset of markdown the model actually
 * writes: paragraphs, line breaks, `-`/`*` and `1.` lists, `**bold**`,
 * `*italic*`, and `` `code` ``. No HTML is ever parsed (React escapes every
 * string), and `_underscores_` are deliberately NOT emphasis: identifiers such
 * as `sample_tiny_input_more_tm` must render exactly as written.
 *
 * An answer interleaves prose with grounded claim/fact chips. Chips are passed
 * in as `slots` and referenced from `source` by a private-use token, so a chip
 * can sit inside a sentence, a list item, or a bold span while the surrounding
 * text is parsed as one string.
 */
const OPEN = "";
const CLOSE = "";

export function slotToken(index: number): string {
  return `${OPEN}${index}${CLOSE}`;
}

// 1: bold, 2: code, 3: italic, 4: slot index. Italic needs a non-space just
// inside each asterisk so "2 * 3" and bullets are left alone.
const INLINE = /\*\*([\s\S]+?)\*\*|`([^`\n]+)`|\*([^\s*](?:[^*\n]*[^\s*])?)\*|(\d+)/g;

function renderInline(text: string, slots: readonly ReactNode[], keyPrefix: string): ReactNode[] {
  const out: ReactNode[] = [];
  let last = 0;
  let n = 0;
  for (const match of text.matchAll(INLINE)) {
    const start = match.index ?? 0;
    if (start > last) out.push(text.slice(last, start));
    const key = `${keyPrefix}-${n++}`;
    if (match[1] !== undefined) {
      out.push(<strong className="font-semibold" key={key}>{renderInline(match[1], slots, key)}</strong>);
    } else if (match[2] !== undefined) {
      out.push(<code className="rounded bg-muted px-1 py-0.5 font-mono text-[0.85em]" key={key}>{match[2]}</code>);
    } else if (match[3] !== undefined) {
      out.push(<em key={key}>{renderInline(match[3], slots, key)}</em>);
    } else {
      // Chips carry a 44px-tall control (target-size rule). Pull the wrapper's
      // margin in so that control keeps its hit area without stretching the
      // text line it sits in.
      out.push(<span className="-my-2.5 inline-block align-middle" key={key}>{slots[Number(match[4])]}</span>);
    }
    last = start + match[0].length;
  }
  if (last < text.length) out.push(text.slice(last));
  return out;
}

type Block =
  | { kind: "p"; lines: string[] }
  | { kind: "h"; text: string }
  | { kind: "ul" | "ol"; items: string[] };

const BULLET = /^\s*[-*•]\s+(.+)$/;
const ORDERED = /^\s*\d+[.)]\s+(.+)$/;
const HEADING = /^\s*#{1,6}\s+(.+)$/;

function parseBlocks(source: string): Block[] {
  const blocks: Block[] = [];
  let current: Block | null = null;
  const close = () => {
    current = null;
  };
  for (const line of source.replace(/\r\n/g, "\n").split("\n")) {
    if (!line.trim()) {
      close();
      continue;
    }
    const heading = HEADING.exec(line);
    if (heading) {
      blocks.push({ kind: "h", text: heading[1] });
      close();
      continue;
    }
    const bullet = BULLET.exec(line);
    const ordered = bullet ? null : ORDERED.exec(line);
    const listKind = bullet ? "ul" : ordered ? "ol" : null;
    if (listKind) {
      const text = (bullet ?? ordered)![1];
      if (current && current.kind === listKind) {
        current.items.push(text);
      } else {
        current = { kind: listKind, items: [text] };
        blocks.push(current);
      }
      continue;
    }
    if (current && current.kind === "p") {
      current.lines.push(line.trim());
    } else {
      current = { kind: "p", lines: [line.trim()] };
      blocks.push(current);
    }
  }
  return blocks;
}

export function AgentText({ slots, source }: Readonly<{ slots: readonly ReactNode[]; source: string }>) {
  const blocks = parseBlocks(source);
  return (
    <div className="space-y-2 text-sm leading-relaxed break-words">
      {blocks.map((block, index) => {
        const key = `b${index}`;
        if (block.kind === "h") {
          return <p className="font-semibold" key={key}>{renderInline(block.text, slots, key)}</p>;
        }
        if (block.kind === "p") {
          return (
            <p key={key}>
              {block.lines.map((line, i) => (
                <Fragment key={`${key}-l${i}`}>
                  {i > 0 ? <br /> : null}
                  {renderInline(line, slots, `${key}-l${i}`)}
                </Fragment>
              ))}
            </p>
          );
        }
        const List = block.kind === "ul" ? "ul" : "ol";
        return (
          <List className={`space-y-1 pl-5 ${block.kind === "ul" ? "list-disc" : "list-decimal"}`} key={key}>
            {block.items.map((item, i) => (
              <li key={`${key}-i${i}`}>{renderInline(item, slots, `${key}-i${i}`)}</li>
            ))}
          </List>
        );
      })}
    </div>
  );
}

/**
 * A verified claim renders its own number AND unit ("22 workers"), and the
 * model is told not to repeat the unit after the placeholder. It sometimes does
 * anyway ("{{r1}} workers in the scenario"), which would read "22 workers
 * workers in the scenario". Drop one repeated unit word from the start of the
 * prose that follows; nothing else about the model's text is touched.
 */
export function stripRepeatedUnit(text: string, unit: string): string {
  const singular = unit.endsWith("s") ? unit.slice(0, -1) : unit;
  return text.replace(new RegExp(`^(\\s*)(?:${unit}|${singular})\\b[ \\t]*`, "i"), "$1");
}
