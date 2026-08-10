export const AUTHOR_TABLE_LIMITS = Object.freeze({
  rows: 50,
  columns: 20,
  cells: 1000,
});

const CELL_DEFAULTS = Object.freeze({
  colspan: 1,
  rowspan: 1,
  colwidth: null,
  align: null,
});

function nodeType(node) {
  return node?.type?.name || node?.type || null;
}

function nodeChildren(node) {
  if (Array.isArray(node?.content)) return node.content;
  const result = [];
  node?.forEach?.((child) => result.push(child));
  return result;
}

function cellAttributesAreDefault(cell) {
  const attributes = cell?.attrs;
  if (!attributes) return true;
  return Object.entries(attributes).every(
    ([name, value]) =>
      Object.hasOwn(CELL_DEFAULTS, name) &&
      (value === undefined || Object.is(value, CELL_DEFAULTS[name])),
  );
}

export function authorTableDimensions(table) {
  if (nodeType(table) !== "table") return null;
  const rows = nodeChildren(table);
  const widths = rows.map((row) => nodeChildren(row).length);
  return {
    rows: rows.length,
    columns: widths[0] || 0,
    cells: widths.reduce((total, width) => total + width, 0),
    widths,
  };
}

function authorTableNodeWithinLimits(table) {
  const dimensions = authorTableDimensions(table);
  if (
    !dimensions ||
    dimensions.rows < 1 ||
    dimensions.rows > AUTHOR_TABLE_LIMITS.rows ||
    dimensions.columns < 1 ||
    dimensions.columns > AUTHOR_TABLE_LIMITS.columns ||
    dimensions.cells > AUTHOR_TABLE_LIMITS.cells ||
    dimensions.widths.some((width) => width !== dimensions.columns)
  ) {
    return false;
  }
  const rows = nodeChildren(table);
  return rows.every((row, rowIndex) => {
    if (nodeType(row) !== "tableRow") return false;
    const cells = nodeChildren(row);
    const expected = rowIndex === 0 ? nodeType(cells[0]) : "tableCell";
    if (!new Set(["tableHeader", "tableCell"]).has(expected)) return false;
    if (rowIndex > 0 && expected !== "tableCell") return false;
    return cells.every(
      (cell) =>
        nodeType(cell) === expected &&
        nodeChildren(cell).length > 0 &&
        cellAttributesAreDefault(cell),
    );
  });
}

export function authorTableDocumentWithinLimits(document) {
  const visit = (node, tableDepth = 0) => {
    const isTable = nodeType(node) === "table";
    if (isTable && (tableDepth > 0 || !authorTableNodeWithinLimits(node))) {
      return false;
    }
    const nextDepth = tableDepth + (isTable ? 1 : 0);
    return nodeChildren(node).every((child) => visit(child, nextDepth));
  };
  return visit(document);
}

export function authorTableCanAddRow(table) {
  if (!authorTableNodeWithinLimits(table)) return false;
  const dimensions = authorTableDimensions(table);
  return (
    dimensions.rows < AUTHOR_TABLE_LIMITS.rows &&
    dimensions.cells + dimensions.columns <= AUTHOR_TABLE_LIMITS.cells
  );
}

export function authorTableCanAddColumn(table) {
  if (!authorTableNodeWithinLimits(table)) return false;
  const dimensions = authorTableDimensions(table);
  return (
    dimensions.columns < AUTHOR_TABLE_LIMITS.columns &&
    dimensions.cells + dimensions.rows <= AUTHOR_TABLE_LIMITS.cells
  );
}
