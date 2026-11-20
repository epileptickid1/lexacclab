"use strict";

const kindLabels = {
  function: "Функція",
  block: "Блок",
  declare: "Оголошення",
  declare_array: "Оголошення масиву",
  initializer_list: "Список початкових значень",
  index: "Елемент масиву",
  assign: "Присвоєння",
  if: "Умова if",
  while: "Цикл while",
  return: "Повернення",
  binary: "Бінарний оператор",
  unary: "Унарний оператор",
  integer: "Ціле число",
  variable: "Змінна",
};

const childRoles = {
  declare: ["змінна", "початкове значення"],
  declare_array: ["масив", "розмір", "початкові значення"],
  index: ["масив", "індекс"],
  assign: ["ціль", "нове значення"],
  if: ["умова", "гілка if", "гілка else"],
  while: ["умова", "тіло циклу"],
  binary: ["лівий операнд", "правий операнд"],
  unary: ["операнд"],
};

const fileInput = document.querySelector("#ast-file");
const status = document.querySelector("#file-status");
const tree = document.querySelector("#tree");
const treeView = document.querySelector("#tree-view");
const source = document.querySelector("#source");
const sourceView = document.querySelector("#source-view");
const sourceLayout = document.querySelector(".source-layout");
const locationLabel = document.querySelector("#source-location");
const lineNumbers = document.querySelector("#line-numbers");
const measure = document.createElement("canvas").getContext("2d");
const mono = getComputedStyle(document.documentElement).getPropertyValue("--mono");

function readAst(json) {
  if (!json || typeof json.file !== "string" || typeof json.source !== "string" || !json.ast) {
    throw new Error("Файл повинен містити назву, вихідний код і дерево синтаксису.");
  }

  const lines = json.source.split("\n");
  let offset = 0;
  const positions = lines.map((line) => {
    const start = offset;
    offset += line.length + 1;
    // Python and JavaScript use different column units for supplementary characters.
    const columns = [start];
    let position = start;
    for (const char of line) {
      position += char.length;
      columns.push(position);
    }
    return columns;
  });

  const ranges = new WeakMap();
  const pending = [json.ast];
  let nodeCount = 0;
  while (pending.length) {
    const node = pending.pop();
    if (!node || !Object.hasOwn(kindLabels, node.kind) || !Array.isArray(node.children) ||
        (node.value != null && !["string", "number"].includes(typeof node.value))) {
      throw new Error("Дерево містить некоректний вузол.");
    }
    const span = node.span;
    if (!span || ![span.line, span.column, span.end_line, span.end_column].every(Number.isInteger)) {
      throw new Error("У вузлі бракує коректної позиції коду.");
    }
    const start = positions[span.line - 1]?.[span.column - 1];
    const end = positions[span.end_line - 1]?.[span.end_column - 1];
    if (start === undefined || end === undefined || end <= start) {
      throw new Error("Позиція вузла виходить за межі фрагмента коду.");
    }
    ranges.set(node, { start, end });
    nodeCount++;
    for (const child of node.children) pending.push(child);
  }
  return { ...json, lineCount: lines.length, nodeCount, ranges };
}

function svgElement(tag, attributes, label) {
  const element = document.createElementNS("http://www.w3.org/2000/svg", tag);
  for (const [name, value] of Object.entries(attributes)) element.setAttribute(name, value);
  if (label !== undefined) element.textContent = label;
  return element;
}

function nodeLabel(node) {
  const { kind, value } = node;
  if (kind === "declare") return "int";
  if (kind === "declare_array") return "int[]";
  if (kind === "index") return "[ ]";
  if (kind === "assign") return "=";
  if (kind === "block") return "{ … }";
  if (kind === "function") return value == null ? kindLabels[kind] : `${value}()`;
  return value == null ? kindLabels[kind] : String(value);
}

function selectNode(ast, node, button) {
  tree.querySelector('[aria-pressed="true"]')?.setAttribute("aria-pressed", "false");
  button.setAttribute("aria-pressed", "true");

  const { start, end } = ast.ranges.get(node);
  const highlight = document.createElement("mark");
  highlight.textContent = ast.source.slice(start, end);
  source.replaceChildren(ast.source.slice(0, start), highlight, ast.source.slice(end));

  const { line, column, end_line, end_column } = node.span;
  locationLabel.textContent = `Рядок і стовпець ${line}:${column} – ${end_line}:${end_column}`;
  const markStart = highlight.getClientRects()[0];
  const viewport = sourceView.getBoundingClientRect();
  if (markStart) {
    const gutter = lineNumbers.getBoundingClientRect().width;
    const left = markStart.left - viewport.left - gutter;
    if (left < 0 || left > viewport.width - gutter - 24) {
      sourceView.scrollLeft += left - 12;
    }
    sourceView.scrollTop += markStart.top - viewport.top - 38;
  }
}

function renderAst(ast) {
  const root = d3.hierarchy(ast.ast);
  d3.tree().nodeSize([58, 1]).separation(() => 1)(root);
  const nodes = [];
  const widths = [];
  let minY = 0;
  let maxY = 0;
  root.eachBefore((node) => {
    node.label = nodeLabel(node.data);
    node.children?.forEach((child, index) => { child.order = index; });
    if (node.parent) {
      const parentKind = node.parent.data.kind;
      node.branch = parentKind === "block" ? String(node.order + 1) : childRoles[parentKind]?.[node.order];
    }

    measure.font = `600 13px ${mono}`;
    const labelWidth = measure.measureText(node.label).width;
    measure.font = `400 11px ${mono}`;
    const branchWidth = node.branch ? measure.measureText(node.branch).width : 0;
    node.width = Math.ceil(Math.max(labelWidth, branchWidth) + 24);
    widths[node.depth] = Math.max(widths[node.depth] || 0, node.width);
    minY = Math.min(minY, node.x);
    maxY = Math.max(maxY, node.x);
    nodes.push(node);
  });

  let left = 20;
  const columns = widths.map((width) => {
    const start = left;
    left += width + 38;
    return start;
  });
  const width = left - 18;
  const height = maxY - minY + 86;
  tree.setAttribute("width", width);
  tree.setAttribute("height", height);
  tree.setAttribute("viewBox", `0 0 ${width} ${height}`);

  const links = svgElement("g", { "aria-hidden": "true" });
  const buttons = document.createDocumentFragment();
  let rootButton;
  for (const node of nodes) {
    const x = columns[node.depth];
    const y = node.x - minY + 43;
    if (node.parent) {
      const parentRight = columns[node.depth - 1] + node.parent.width;
      const parentY = node.parent.x - minY + 43;
      const midpoint = (parentRight + x) / 2;
      links.append(svgElement("path", {
        class: "tree-link",
        d: `M ${parentRight} ${parentY} C ${midpoint} ${parentY}, ${midpoint} ${y}, ${x} ${y}`,
      }));
    }

    const kind = node.data.kind;
    const operator = ["binary", "unary", "assign"].includes(kind);
    const name = [node.branch, kindLabels[kind], node.data.value].filter((part) => part != null).join(", ");
    const button = svgElement("g", {
      class: operator ? "tree-node operator" : "tree-node",
      transform: `translate(${x}, ${y})`,
      role: "button",
      tabindex: "0",
      "aria-label": name,
      "aria-pressed": "false",
    });
    button.append(svgElement("title", {}, name));
    button.append(svgElement("rect", { y: -22, width: node.width, height: 44, rx: 7 }));
    if (node.branch) {
      button.append(svgElement("text", { class: "node-role", x: 12, y: -8 }, node.branch));
    }
    button.append(svgElement("text", { x: 12, y: node.branch ? 8 : 0 }, node.label));
    button.addEventListener("click", () => selectNode(ast, node.data, button));
    button.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        selectNode(ast, node.data, button);
      }
    });
    buttons.append(button);
    if (!node.parent) rootButton = button;
  }

  tree.replaceChildren(links, buttons);
  lineNumbers.textContent = Array.from({ length: ast.lineCount }, (_, index) => index + 1).join("\n");
  treeView.querySelector(".empty").hidden = true;
  sourceView.querySelector(".empty").hidden = true;
  tree.removeAttribute("hidden");
  sourceLayout.hidden = false;
  treeView.scrollLeft = 0;
  treeView.scrollTop = root.x - minY - treeView.clientHeight / 2 + 43;
  sourceView.scrollLeft = 0;
  sourceView.scrollTop = 0;
  selectNode(ast, ast.ast, rootButton);
}

fileInput.addEventListener("change", async () => {
  const file = fileInput.files[0];
  if (!file) return;
  status.classList.remove("error");
  status.textContent = "Читання файлу…";

  try {
    const contents = await file.text();
    if (fileInput.files[0] !== file) return;
    const ast = readAst(JSON.parse(contents));
    if (!window.d3?.hierarchy || !window.d3?.tree) {
      throw new Error("Не вдалося завантажити локальну бібліотеку D3.");
    }
    renderAst(ast);
    status.textContent = `${ast.file} · Кількість вузлів ${ast.nodeCount}`;
  } catch (error) {
    if (fileInput.files[0] !== file) return;
    status.classList.add("error");
    const reason = error instanceof SyntaxError ? "Некоректний JSON." : error.message;
    const previous = tree.hasAttribute("hidden") ? "" : " Залишено попереднє дерево.";
    status.textContent = `Не вдалося відкрити ${file.name}. ${reason}${previous}`;
  }
});
