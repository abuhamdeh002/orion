import { Fragment, ReactNode } from "react";

/**
 * Light formatting for replies: paragraphs, **bold**, *italic*, `code`, lists and links.
 * Built from React elements only (never innerHTML), so a reply can't inject markup.
 */
export function Rich({ text }: { text: string }) {
  const blocks = text.replace(/\r/g, "").split(/\n{2,}/);
  return (
    <>
      {blocks.map((block, index) => {
        const lines = block.split("\n").filter((line) => line.trim() !== "");
        if (lines.length > 0 && lines.every((line) => /^\s*[-*•]\s+/.test(line))) {
          return (
            <ul key={index} className="rich-list">
              {lines.map((line, item) => <li key={item}>{inline(line.replace(/^\s*[-*•]\s+/, ""))}</li>)}
            </ul>
          );
        }
        if (lines.length > 0 && lines.every((line) => /^\s*\d+[.)]\s+/.test(line))) {
          return (
            <ol key={index} className="rich-list">
              {lines.map((line, item) => <li key={item}>{inline(line.replace(/^\s*\d+[.)]\s+/, ""))}</li>)}
            </ol>
          );
        }
        if (/^```/.test(block.trim())) {
          return <pre key={index} className="rich-code"><code>{block.trim().replace(/^```\w*\n?|```$/g, "")}</code></pre>;
        }
        return (
          <p key={index} className="rich-p">
            {lines.map((line, row) => (
              <Fragment key={row}>
                {row > 0 && <br />}
                {inline(line.replace(/^#{1,6}\s+/, ""))}
              </Fragment>
            ))}
          </p>
        );
      })}
    </>
  );
}

const TOKEN = /(\*\*[^*]+\*\*|\*[^*\s][^*]*\*|`[^`]+`|https?:\/\/[^\s)]+)/g;

function inline(text: string): ReactNode[] {
  return text.split(TOKEN).map((part, index) => {
    if (!part) return null;
    if (part.startsWith("**") && part.endsWith("**")) return <strong key={index}>{part.slice(2, -2)}</strong>;
    if (part.startsWith("`") && part.endsWith("`")) return <code key={index} className="rich-inline">{part.slice(1, -1)}</code>;
    if (part.startsWith("*") && part.endsWith("*") && part.length > 2) return <em key={index}>{part.slice(1, -1)}</em>;
    if (/^https?:\/\//.test(part)) {
      return (
        <a key={index} href={part} target="_blank" rel="noopener noreferrer">
          {part.replace(/^https?:\/\/(www\.)?/, "").slice(0, 48)}
        </a>
      );
    }
    return <Fragment key={index}>{part}</Fragment>;
  });
}
