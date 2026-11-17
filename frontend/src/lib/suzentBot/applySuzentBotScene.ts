import type {
  SceneFrame,
  SceneNode,
} from '../../../../packages/suzent-bot-core/src/suzentBotScene';

const SVG_NS = 'http://www.w3.org/2000/svg';

function createNode(node: SceneNode): SVGElement {
  const element = document.createElementNS(SVG_NS, node.tag);
  for (const [key, value] of Object.entries(node.attrs)) element.setAttribute(key, value);
  if (node.display) element.style.display = node.display;
  if (node.opacity) element.style.opacity = node.opacity;
  for (const child of node.children) element.appendChild(createNode(child));
  return element;
}

/** Paint one scene frame into the live SVG. The engine never touches the DOM itself. */
export function applySuzentBotScene(svg: SVGSVGElement, frame: SceneFrame): void {
  svg.setAttribute('viewBox', frame.viewBox);
  svg.style.setProperty('--fg', frame.fg);
  svg.style.setProperty('--bg', frame.bg);
  svg.replaceChildren(...frame.nodes.map(createNode));
}
