/** The Orion constellation as seen from the northern hemisphere, in a -1..1 box. */
export type StarName = "meissa" | "betelgeuse" | "bellatrix" | "alnitak" | "alnilam" | "mintaka" | "saiph" | "rigel";

export type Star = { name: StarName; x: number; y: number; size: number; tone: "warm" | "cool" | "white" };

export const STARS: Star[] = [
  { name: "meissa", x: 0.0, y: -0.8, size: 0.55, tone: "white" },
  { name: "betelgeuse", x: -0.46, y: -0.5, size: 1.15, tone: "warm" },
  { name: "bellatrix", x: 0.4, y: -0.42, size: 0.8, tone: "cool" },
  { name: "alnitak", x: -0.15, y: 0.04, size: 0.72, tone: "cool" },
  { name: "alnilam", x: 0.0, y: -0.03, size: 0.78, tone: "cool" },
  { name: "mintaka", x: 0.15, y: -0.1, size: 0.7, tone: "cool" },
  { name: "saiph", x: -0.34, y: 0.66, size: 0.78, tone: "cool" },
  { name: "rigel", x: 0.48, y: 0.58, size: 1.1, tone: "cool" },
];

const index = (name: StarName) => STARS.findIndex((star) => star.name === name);

/** Lines of the figure: head, shoulders, belt, legs. */
export const LINES: [number, number][] = [
  [index("meissa"), index("betelgeuse")],
  [index("meissa"), index("bellatrix")],
  [index("betelgeuse"), index("alnitak")],
  [index("bellatrix"), index("mintaka")],
  [index("alnitak"), index("alnilam")],
  [index("alnilam"), index("mintaka")],
  [index("alnitak"), index("saiph")],
  [index("mintaka"), index("rigel")],
];

export const BELT = [index("alnitak"), index("alnilam"), index("mintaka")];
