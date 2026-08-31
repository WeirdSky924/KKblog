import { cp, mkdir, rm } from "node:fs/promises";
import path from "node:path";

const source = path.resolve(
  "node_modules/@fontsource-variable/noto-sans-sc/files",
);
const destination = path.resolve("static/dist/files");
const katexSource = path.resolve("node_modules/katex/dist/fonts");
const katexDestination = path.resolve("static/dist/fonts");

await rm(destination, { recursive: true, force: true });
await rm(katexDestination, { recursive: true, force: true });
await mkdir(path.dirname(destination), { recursive: true });
await cp(source, destination, { recursive: true });
await mkdir(katexDestination, { recursive: true });
await cp(katexSource, katexDestination, { recursive: true });
