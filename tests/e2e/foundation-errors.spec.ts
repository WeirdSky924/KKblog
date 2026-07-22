import { execFileSync } from "node:child_process";

import { expect, test } from "@playwright/test";

import {
  identityNames,
  type IdentityName,
  storageStateEnvironmentFor,
  storageStateFor,
} from "./identity";

const cliPath = "/usr/local/bin/blog-playwright-cli";

function run(session: string, ...args: string[]): string {
  return execFileSync(cliPath, [`-s=${session}`, ...args], {
    cwd: process.cwd(),
    encoding: "utf8",
    timeout: 60_000,
  });
}

test("identity project has an explicit isolated state contract", async ({}, testInfo) => {
  const identity = testInfo.project.name as IdentityName;
  expect(identityNames).toContain(identity);
  const stateEnvironment = storageStateEnvironmentFor(identity);
  if (identity === "visitor") {
    expect(stateEnvironment).toBeUndefined();
    expect(storageStateFor(identity)).toBeUndefined();
    return;
  }
  if (!stateEnvironment) {
    throw new Error(`Missing state environment contract for ${identity}`);
  }
  expect(stateEnvironment).toBe(`KAJ_E2E_${identity.toUpperCase()}_STATE`);
  if (process.env[stateEnvironment]) {
    expect(storageStateFor(identity)).toBeTruthy();
  }
});

test("unified errors support real responsive keyboard recovery", async ({}, testInfo) => {
  const identity = testInfo.project.name as IdentityName;
  const storageEnvironment = storageStateEnvironmentFor(identity);
  test.skip(
    Boolean(storageEnvironment && !process.env[storageEnvironment]),
    "Authenticated storage states are created by the accounts phase",
  );
  const storageState = storageStateFor(identity);
  const session = `fnd006-${process.pid}`;
  try {
    run(session, "open", "http://127.0.0.1:8766/ready/");
    if (storageState) {
      run(session, "state-load", storageState);
      run(session, "goto", "http://127.0.0.1:8766/ready/");
    }
    run(session, "resize", "390", "844");
    run(session, "click", "text=打开错误页");
    const snapshot = run(session, "snapshot");
    expect(snapshot).toContain('heading "页面暂时无法显示"');
    expect(snapshot).toMatch(/trc_[0-9a-hjkmnp-tv-z]{26}/);
    run(
      session,
      "eval",
      `async () => {
        await document.fonts.ready;
        const button = document.querySelector("[data-error-back]");
        const rect = button.getBoundingClientRect();
        if (document.documentElement.scrollWidth !== innerWidth) throw new Error("overflow");
        if (!document.fonts.check("16px Noto Sans SC Variable")) throw new Error("font");
        if (rect.height < 44 || rect.width < 44) throw new Error("target-size");
        document.documentElement.dataset.theme = "dark";
      }`,
    );
    const requests = run(session, "requests", "--static");
    expect(requests).not.toMatch(/\/static\/.*=> \[(?!200|304\])/);
    run(
      session,
      "screenshot",
      `--filename=/tmp/fnd006-500-390-dark-${process.pid}.png`,
    );

    run(session, "press", "Tab");
    run(session, "press", "Tab");
    run(
      session,
      "eval",
      `() => {
        if (document.activeElement?.textContent?.trim() !== "返回上一页") {
          throw new Error("focus");
        }
        if (getComputedStyle(document.activeElement).outlineStyle === "none") {
          throw new Error("focus-ring");
        }
      }`,
    );
    run(session, "press", "Enter");
    run(
      session,
      "eval",
      `() => {
        if (location.pathname !== "/ready/") throw new Error("history-recovery");
        if (document.activeElement?.id !== "error-page-trigger") {
          throw new Error("focus-recovery");
        }
      }`,
    );

    run(session, "goto", "http://127.0.0.1:8766/not-found/");
    run(session, "resize", "768", "1024");
    run(
      session,
      "eval",
      `() => {
        document.documentElement.dataset.theme = "eye-care";
        if (document.documentElement.scrollWidth !== innerWidth) throw new Error("overflow");
      }`,
    );
    run(
      session,
      "screenshot",
      `--filename=/tmp/fnd006-404-768-eye-care-${process.pid}.png`,
    );
    run(session, "resize", "1440", "900");
    run(
      session,
      "eval",
      `() => {
        document.documentElement.dataset.theme = "light";
        if (document.documentElement.scrollWidth !== innerWidth) throw new Error("overflow");
      }`,
    );
    run(
      session,
      "screenshot",
      `--filename=/tmp/fnd006-404-1440-light-${process.pid}.png`,
    );

    run(session, "goto", "http://127.0.0.1:8766/error/422/");
    expect(run(session, "snapshot")).toContain("请检查输入后重试");
  } finally {
    try {
      run(session, "close");
    } catch {
      // The session may not exist when setup itself failed.
    }
  }
});
