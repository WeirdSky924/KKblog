"use strict";

const fs = require("node:fs");
const { COLLECTORS, CONTRACTS } = require("./browser_collectors.cjs");
const {
  CollectorError,
  ERROR,
  parseRequest,
} = require("./browser_runtime.cjs");

function write(value) {
  process.stdout.write(JSON.stringify(value));
}

async function main() {
  let raw;
  let incoming = {};
  try {
    raw = fs.readFileSync(0);
    if (raw.length < 2 || raw.length > 16384) {
      throw new CollectorError(ERROR.invalid);
    }
    incoming = JSON.parse(raw.toString("utf8"));
    const request = parseRequest(incoming, CONTRACTS);
    const output = await COLLECTORS[request.collector](request);
    write(output);
  } catch (error) {
    const code =
      error instanceof CollectorError
        ? error.code
        : error?.name === "TimeoutError"
          ? ERROR.timeout
          : ERROR.failed;
    write({
      version: 1,
      collector:
        typeof incoming?.collector === "string" ? incoming.collector : "invalid",
      error_code: code,
    });
    process.exitCode = 2;
  }
}

main();
