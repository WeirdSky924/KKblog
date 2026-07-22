import { cp, mkdir, rm } from "node:fs/promises";
import path from "node:path";

const source = path.resolve(
  "node_modules/@fontsource-variable/noto-sans-sc/files",
);
const destination = path.resolve("static/dist/files");

await rm(destination, { recursive: true, force: true });
await mkdir(path.dirname(destination), { recursive: true });
await cp(source, destination, { recursive: true });
