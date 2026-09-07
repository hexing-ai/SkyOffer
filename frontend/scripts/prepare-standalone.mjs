import { cpSync, existsSync, mkdirSync, rmSync } from "node:fs";
import { dirname, resolve } from "node:path";

const copies = [
  [resolve(".next/static"), resolve(".next/standalone/.next/static")],
  [resolve("public"), resolve(".next/standalone/public")],
];

for (const [source, destination] of copies) {
  if (!existsSync(source)) continue;
  rmSync(destination, { force: true, recursive: true });
  mkdirSync(dirname(destination), { recursive: true });
  cpSync(source, destination, { recursive: true });
}
