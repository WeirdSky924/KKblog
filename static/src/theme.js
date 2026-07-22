import { normalizeTheme, readStoredTheme } from "./theme-values.js";

const root = document.documentElement;
const initialTheme =
  readStoredTheme() ?? normalizeTheme(root.dataset.theme) ?? "light";

root.dataset.theme = initialTheme;
