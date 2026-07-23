import {
  normalizeTheme,
  readStoredTheme,
  storeTheme,
} from "./theme-values.js";

const root = document.documentElement;
const accountTheme =
  root.dataset.themeSource === "account" ? normalizeTheme(root.dataset.theme) : null;
const initialTheme =
  accountTheme ?? readStoredTheme() ?? normalizeTheme(root.dataset.theme) ?? "light";

root.dataset.theme = initialTheme;
if (accountTheme) {
  storeTheme(accountTheme);
}
