type Tag = "h2" | "h3";

/**
 * A headline that arrives word by word. In "Good evening, Sir." the part after the
 * comma is set in italic, the way a person would lean on it.
 */
export function Alive({ text, tag: TagName = "h2" }: { text: string; tag?: Tag }) {
  const split = text.indexOf(", ");
  const head = split > 0 ? text.slice(0, split + 1) : text;
  const tail = split > 0 ? text.slice(split + 2) : "";
  let order = 0;
  const words = (part: string, lean: boolean) =>
    part.split(" ").map((word) => {
      const delay = 0.08 * order++;
      return (
        <span key={`${word}-${order}`} className={lean ? "word lean" : "word"} style={{ animationDelay: `${delay}s` }}>
          {word}{" "}
        </span>
      );
    });
  return (
    <TagName className="alive" aria-label={text}>
      {words(head, false)}
      {tail && words(tail, true)}
    </TagName>
  );
}
