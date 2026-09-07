import { spawn } from "node:child_process";
const build = process.argv.includes("--build");
const child = spawn(process.execPath, ["node_modules/next/dist/bin/next", ...(build ? ["build", "--webpack"] : ["dev", "--hostname", "127.0.0.1", "--port", "3200"])], {
  stdio: "inherit", env: { ...process.env, NEXT_PUBLIC_DEMO_MODE: "1" },
});
child.on("exit", code => process.exit(code ?? 1));
for (const signal of ["SIGINT", "SIGTERM"]) process.on(signal, () => child.kill(signal));
