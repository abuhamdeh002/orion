const paths = {
  chat: "M4 5.5h16v10H9l-5 4v-14Z",
  skills: "M4 4h7v7H4zM13 4h7v7h-7zM4 13h7v7H4zM13 13h7v7h-7z",
  memory: "M12 3a6 6 0 0 0-6 6c0 2.4 1.3 3.6 2.4 4.7.8.8 1.1 1.5 1.1 2.3V17h5v-1c0-.8.3-1.5 1.1-2.3C16.7 12.6 18 11.4 18 9a6 6 0 0 0-6-6ZM9.5 20.5h5",
  settings: "M12 8.5a3.5 3.5 0 1 0 0 7 3.5 3.5 0 0 0 0-7ZM12 2.5v3M12 18.5v3M2.5 12h3M18.5 12h3M5.3 5.3l2.1 2.1M16.6 16.6l2.1 2.1M5.3 18.7l2.1-2.1M16.6 7.4l2.1-2.1",
  send: "M5 12h13M13 6l6 6-6 6",
  stop: "M7 7h10v10H7z",
  play: "M8 5.5v13l10-6.5-10-6.5Z",
  check: "M5 12.5l4.5 4.5L19 7.5",
  cross: "M6.5 6.5l11 11M17.5 6.5l-11 11",
  plus: "M12 5v14M5 12h14",
  mic: "M12 3.5a3 3 0 0 0-3 3v5a3 3 0 0 0 6 0v-5a3 3 0 0 0-3-3ZM7 11.5a5 5 0 0 0 10 0M12 16.5v4",
  image: "M4 6.5h3l1.5-2h7L17 6.5h3v12H4zM12 9.5a3.5 3.5 0 1 0 0 7 3.5 3.5 0 0 0 0-7Z",
  bell: "M6.5 16.5V11a5.5 5.5 0 0 1 11 0v5.5l1.5 1.5H5l1.5-1.5ZM10 20.5h4",
  sun: "M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8ZM12 2.5v2M12 19.5v2M4.6 4.6l1.4 1.4M18 18l1.4 1.4M2.5 12h2M19.5 12h2M4.6 19.4 6 18M18 6l1.4-1.4",
  chip: "M7 7h10v10H7zM10 10h4v4h-4zM9.5 3.5V7M14.5 3.5V7M9.5 17v3.5M14.5 17v3.5M3.5 9.5H7M3.5 14.5H7M17 9.5h3.5M17 14.5h3.5",
  moon: "M19.5 14.5A7.5 7.5 0 0 1 9.5 4.5a7.5 7.5 0 1 0 10 10Z",
  copy: "M8.5 8.5h11v11h-11zM15.5 8.5v-4h-11v11h4",
  speaker: "M4.5 9.5h3l4.5-4v13l-4.5-4h-3zM15.5 9a4 4 0 0 1 0 6M17.8 6.5a7.5 7.5 0 0 1 0 11",
  search: "M10.5 4.5a6 6 0 1 0 0 12 6 6 0 0 0 0-12ZM15 15l4.5 4.5",
  swatch: "M12 3.5a8.5 8.5 0 1 0 0 17c1.1 0 1.8-.8 1.8-1.7 0-.5-.2-.9-.5-1.2-.3-.3-.4-.7-.4-1.1 0-.9.7-1.6 1.6-1.6H16a4.5 4.5 0 0 0 4.5-4.5C20.5 6.7 16.7 3.5 12 3.5ZM7.5 12h.01M9.5 8h.01M14.5 8h.01",
  sparkle: "M12 3.5l1.8 5.2 5.2 1.8-5.2 1.8L12 17.5l-1.8-5.2L5 10.5l5.2-1.8ZM18.5 15.5l.7 2 2 .7-2 .7-.7 2-.7-2-2-.7 2-.7Z",
  trash: "M5.5 7h13M9.5 7V4.5h5V7M7 7l1 12.5h8L17 7",
  wave: "M4 10v4M8 7v10M12 4v16M16 8v8M20 11v2",
  compose: "M12.5 5.5H6a1.5 1.5 0 0 0-1.5 1.5v11A1.5 1.5 0 0 0 6 19.5h11a1.5 1.5 0 0 0 1.5-1.5v-6.5M17.6 4.4a1.6 1.6 0 0 1 2.3 2.3L12 14.5l-3 .7.7-3 7.9-7.8Z",
} as const;

export type IconName = keyof typeof paths;

export function Icon({ name }: { name: IconName }) {
  return (
    <svg className="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d={paths[name]} />
    </svg>
  );
}
