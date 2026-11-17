/**
 * Render-agnostic scene graph for the Suzent bot.
 *
 * The engine writes this virtual tree instead of a live SVG document. Desktop,
 * iOS, and Android each walk the same plain `SceneFrame` data.
 */

import {
  HEAD_C,
  SUZENT_BODY_PATH,
  SUZENT_EXPRESSIONS,
  ringPath,
} from "./suzentBotGeometry";

export const SUZENT_VIEWBOX = "-46 -46 320.54 320.54";

export interface SceneNode {
  tag: string;
  attrs: Record<string, string>;
  display?: string;
  opacity?: string;
  children: SceneNode[];
}

export interface SceneFrame {
  viewBox: string;
  fg: string;
  bg: string;
  settled: boolean;
  nodes: SceneNode[];
}

export interface SceneBounds {
  left: number;
  top: number;
  width: number;
  height: number;
  right: number;
  bottom: number;
}

export class VStyle {
  display = "";
  opacity = "";

  constructor(private readonly owner: VElement) {}

  setProperty(name: string, value: string): void {
    this.owner.vars[name] = value;
  }
}

/**
 * The subset of SVGElement the engine and particle system actually touch.
 * Attribute writes stay strings, matching the historical `setAttribute` output.
 */
export class VElement {
  readonly attrs: Record<string, string> = {};
  readonly children: VElement[] = [];
  readonly vars: Record<string, string> = {};
  readonly style: VStyle;
  parent: VElement | null = null;
  bounds: SceneBounds = {
    left: 0,
    top: 0,
    width: 36,
    height: 36,
    right: 36,
    bottom: 36,
  };

  constructor(readonly tag: string) {
    this.style = new VStyle(this);
  }

  get id(): string {
    return this.attrs.id ?? "";
  }

  setAttribute(name: string, value: string): void {
    if (name === "style") {
      this.style.display = "";
      this.style.opacity = "";
      for (const part of value.split(";")) {
        const split = part.indexOf(":");
        if (split < 0) continue;
        const key = part.slice(0, split).trim();
        const val = part.slice(split + 1).trim();
        if (key === "display") this.style.display = val;
        if (key === "opacity") this.style.opacity = val;
      }
      return;
    }
    this.attrs[name] = value;
  }

  getAttribute(name: string): string | null {
    return this.attrs[name] ?? null;
  }

  removeAttribute(name: string): void {
    delete this.attrs[name];
  }

  appendChild(child: VElement): VElement {
    child.remove();
    child.parent = this;
    this.children.push(child);
    return child;
  }

  insertBefore(child: VElement, before: VElement | null): VElement {
    child.remove();
    child.parent = this;
    const index = before ? this.children.indexOf(before) : -1;
    if (index < 0) this.children.push(child);
    else this.children.splice(index, 0, child);
    return child;
  }

  remove(): void {
    if (!this.parent) return;
    const index = this.parent.children.indexOf(this);
    if (index >= 0) this.parent.children.splice(index, 1);
    this.parent = null;
  }

  get innerHTML(): string {
    return this.children.map((child) => serializeSvg(child)).join("");
  }

  set innerHTML(html: string) {
    this.children.splice(0, this.children.length);
    for (const child of parseSvgFragment(html)) this.appendChild(child);
  }

  querySelector(selector: string): VElement | null {
    return this.querySelectorAll(selector)[0] ?? null;
  }

  querySelectorAll(selector: string): VElement[] {
    const matches: VElement[] = [];
    const visit = (node: VElement) => {
      for (const child of node.children) {
        if (matchesSelector(child, selector)) matches.push(child);
        visit(child);
      }
    };
    visit(this);
    return matches;
  }

  getBoundingClientRect(): SceneBounds {
    return this.bounds;
  }
}

function matchesSelector(node: VElement, selector: string): boolean {
  if (selector.startsWith("#")) return node.attrs.id === selector.slice(1);
  if (selector.startsWith(".")) {
    const name = selector.slice(1);
    return (node.attrs.class ?? "").split(/\s+/).includes(name);
  }
  return node.tag === selector;
}

export function parseSvgFragment(html: string): VElement[] {
  const roots: VElement[] = [];
  const stack: VElement[] = [];
  const pattern = /<!--[\s\S]*?-->|<(\/)?([A-Za-z][\w:.-]*)([^>]*?)(\/?)>/g;
  let match: RegExpExecArray | null;
  while ((match = pattern.exec(html))) {
    const closing = Boolean(match[1]);
    const tag = match[2].toLowerCase();
    const selfClosing = Boolean(match[4]) || closing;
    if (closing) {
      for (let i = stack.length - 1; i >= 0; i -= 1) {
        if (stack[i].tag === tag) {
          stack.splice(i);
          break;
        }
      }
      continue;
    }
    const element = new VElement(tag);
    applyAttributeMarkup(element, match[3] ?? "");
    const parent = stack[stack.length - 1];
    if (parent) parent.appendChild(element);
    else roots.push(element);
    if (!selfClosing) stack.push(element);
  }
  return roots;
}

function applyAttributeMarkup(element: VElement, source: string): void {
  const pattern = /([:@\w.-]+)(?:\s*=\s*(?:"([^"]*)"|'([^']*)'|(\S+)))?/g;
  let match: RegExpExecArray | null;
  while ((match = pattern.exec(source))) {
    const value = match[2] ?? match[3] ?? match[4] ?? "";
    element.setAttribute(match[1], value);
  }
}

function serializeSvg(node: VElement): string {
  const attrs = Object.entries(node.attrs)
    .map(([key, value]) => `${key}="${value}"`)
    .join(" ");
  const open = attrs ? `<${node.tag} ${attrs}>` : `<${node.tag}>`;
  return `${open}${node.children.map((child) => serializeSvg(child)).join("")}</${node.tag}>`;
}

function sortedAttrs(attrs: Record<string, string>): Record<string, string> {
  const sorted: Record<string, string> = {};
  for (const key of Object.keys(attrs).sort()) sorted[key] = attrs[key];
  return sorted;
}

export function serializeNode(node: VElement): SceneNode | null {
  const display = node.style.display;
  const children = node.children
    .map((child) => serializeNode(child))
    .filter((child): child is SceneNode => child !== null);
  if (display === "none" && children.length === 0) return null;
  const scene: SceneNode = {
    tag: node.tag,
    attrs: sortedAttrs(node.attrs),
    children,
  };
  if (display && display !== "none") scene.display = display;
  if (node.style.opacity) scene.opacity = node.style.opacity;
  return scene;
}

export function sceneFromTree(
  root: VElement,
  options: { fg: string; bg: string; settled: boolean },
): SceneFrame {
  return {
    viewBox: root.attrs.viewBox ?? SUZENT_VIEWBOX,
    fg: options.fg,
    bg: options.bg,
    settled: options.settled,
    nodes: root.children
      .map((child) => serializeNode(child))
      .filter((child): child is SceneNode => child !== null),
  };
}

export interface BotTreeIds {
  svgId: string;
  clipId: string;
  size?: number;
}

/** The same static skeleton SuzentBotMark used to declare in JSX. */
export function buildSuzentBotTree({
  svgId,
  clipId,
  size = 36,
}: BotTreeIds): VElement {
  const svg = new VElement("svg");
  svg.setAttribute("id", svgId);
  svg.setAttribute("viewBox", SUZENT_VIEWBOX);
  svg.bounds = {
    left: 0,
    top: 0,
    width: size,
    height: size,
    right: size,
    bottom: size,
  };

  const defs = svg.appendChild(new VElement("defs"));
  const clip = defs.appendChild(new VElement("clipPath"));
  clip.setAttribute("id", clipId);
  const clipPath = clip.appendChild(new VElement("path"));
  clipPath.setAttribute("id", "head-clip-path");
  clipPath.setAttribute("d", SUZENT_BODY_PATH);

  const back = svg.appendChild(new VElement("g"));
  back.setAttribute("id", "particles-back");
  const actBack = svg.appendChild(new VElement("g"));
  actBack.setAttribute("class", "suzent-act-back");

  const hidden = (
    tag: string,
    className: string,
    filled: boolean,
  ): VElement => {
    const el = svg.appendChild(new VElement(tag));
    el.setAttribute("class", className);
    if (filled) el.setAttribute("fill", "var(--fg)");
    if (tag === "circle") {
      el.setAttribute("cx", String(HEAD_C));
      el.setAttribute("cy", String(HEAD_C));
      el.setAttribute("r", "0");
    }
    if (tag === "path" && className.includes("morph-head"))
      el.setAttribute("d", SUZENT_BODY_PATH);
    el.style.display = "none";
    return el;
  };
  for (let i = 0; i < 2; i += 1)
    hidden("path", "grok-bot-mark__head morph-head", true);
  for (let i = 0; i < 5; i += 1) hidden("circle", "morph-ring", false);
  for (let i = 0; i < 5; i += 1)
    hidden("circle", "grok-bot-mark__head morph-part", true);
  for (let i = 0; i < 3; i += 1) hidden("path", "morph-glyph", false);

  const transform = svg.appendChild(new VElement("g"));
  transform.setAttribute("id", "bot-transform");
  const head = transform.appendChild(new VElement("path"));
  head.setAttribute("id", "head-path");
  head.setAttribute("class", "grok-bot-mark__head");
  head.setAttribute("d", SUZENT_BODY_PATH);
  head.setAttribute("fill", "var(--fg)");

  const clipped = transform.appendChild(new VElement("g"));
  clipped.setAttribute("clip-path", `url(#${clipId})`);
  const eyes = clipped.appendChild(new VElement("g"));
  eyes.setAttribute("id", "eyes-group");
  for (const ring of [SUZENT_EXPRESSIONS[0][0], SUZENT_EXPRESSIONS[0][1]]) {
    const eye = eyes.appendChild(new VElement("path"));
    eye.setAttribute("class", "grok-bot-mark__eye eye-path");
    eye.setAttribute("d", ringPath(ring));
    eye.setAttribute("fill", "var(--bg)");
  }

  const badge = transform.appendChild(new VElement("circle"));
  badge.setAttribute("id", "notify-badge");
  badge.setAttribute("cx", "198");
  badge.setAttribute("cy", "40");
  badge.setAttribute("r", "0");
  badge.style.display = "none";

  const actFront = svg.appendChild(new VElement("g"));
  actFront.setAttribute("class", "suzent-act-front");
  const front = svg.appendChild(new VElement("g"));
  front.setAttribute("id", "particles-front");
  return svg;
}

/** Mulberry32. Integer math stays inside 2^53 so every JS host agrees. */
export function mulberry32(seed: number): () => number {
  let state = seed >>> 0;
  return () => {
    state = (state + 0x6d2b79f5) >>> 0;
    let t = Math.imul(state ^ (state >>> 15), state | 1);
    t = (t + Math.imul(t ^ (t >>> 7), t | 61)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/**
 * Rhino's `Math.imul` is missing, and the embed target rewrites it. This
 * variant is what the shared bundle and the native hosts actually run.
 */
export function portableMulberry32(seed: number): () => number {
  let state = seed >>> 0;
  const imul = (a: number, b: number) => {
    const aHi = (a >>> 16) & 0xffff;
    const aLo = a & 0xffff;
    const bHi = (b >>> 16) & 0xffff;
    const bLo = b & 0xffff;
    return (aLo * bLo + ((aHi * bLo + aLo * bHi) << 16)) | 0;
  };
  return () => {
    state = (state + 0x6d2b79f5) >>> 0;
    let t = imul(state ^ (state >>> 15), state | 1);
    t = (t + imul(t ^ (t >>> 7), t | 61)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}
