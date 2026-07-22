export const THEME_STORAGE_KEY = "kaj.theme";
export const THEME_NAMES = Object.freeze(["light", "dark", "eye-care"]);

export function normalizeTheme(value) {
  return typeof value === "string" && THEME_NAMES.includes(value) ? value : null;
}

export function readStoredTheme() {
  try {
    return normalizeTheme(window.localStorage.getItem(THEME_STORAGE_KEY));
  } catch {
    return null;
  }
}

export function storeTheme(theme) {
  try {
    window.localStorage.setItem(THEME_STORAGE_KEY, theme);
  } catch {
    // Storage can be unavailable in privacy modes; the active page still updates.
  }
}
