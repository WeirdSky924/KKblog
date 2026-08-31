"use strict";

const fs = require("node:fs");
const path = require("node:path");
const { chromium } = require("playwright");

const ERROR = Object.freeze({
  denied: "opportunities.adapter_browser_denied.v1",
  failed: "opportunities.adapter_browser_failed.v1",
  invalid: "opportunities.adapter_browser_response_invalid.v1",
  timeout: "opportunities.collection_timeout.v1",
  upstream: "opportunities.adapter_response_invalid.v1",
  upstreamChannel: "opportunities.adapter_channel_invalid.v1",
  upstreamFields: "opportunities.adapter_fields_invalid.v1",
  upstreamPaging: "opportunities.adapter_paging_invalid.v1",
});

class CollectorError extends Error {
  constructor(code) {
    super(code);
    this.code = code;
  }
}

function assertObject(value) {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new CollectorError(ERROR.invalid);
  }
  return value;
}

function text(value, maximum = 300) {
  if (typeof value !== "string") return "";
  return value.replace(/\s+/gu, " ").trim().slice(0, maximum);
}

function labels(values) {
  if (!Array.isArray(values)) return [];
  return [...new Set(values.map((value) => text(value, 100)).filter(Boolean))];
}

function cohortLabels(...values) {
  const found = [];
  for (const value of values) {
    for (const match of text(value, 400).matchAll(/(?<!\d)(?:20)?\d{2}\s*届/gu)) {
      const normalized = match[0].replace(/\s+/gu, "");
      found.push(normalized.length === 3 ? `20${normalized}` : normalized);
    }
  }
  return labels(found);
}

function parseRequest(value, contracts) {
  const request = assertObject(value);
  const exactKeys = [
    "version",
    "collector",
    "source_url",
    "allowed_hosts",
    "max_pages",
    "max_opportunities",
    "timeout_ms",
  ];
  if (
    Object.keys(request).sort().join("|") !== exactKeys.sort().join("|") ||
    request.version !== 1 ||
    !Object.hasOwn(contracts, request.collector)
  ) {
    throw new CollectorError(ERROR.denied);
  }
  const contract = contracts[request.collector];
  let source;
  try {
    source = new URL(request.source_url);
  } catch {
    throw new CollectorError(ERROR.denied);
  }
  const sourceHosts = contract.sourceHosts || new Set([contract.sourceHost]);
  if (
    source.protocol !== "https:" ||
    !sourceHosts.has(source.hostname) ||
    !contract.sourcePath(source) ||
    !Array.isArray(request.allowed_hosts) ||
    request.allowed_hosts.length !== 1 ||
    request.allowed_hosts[0] !== source.hostname ||
    !Number.isInteger(request.max_pages) ||
    request.max_pages < 1 ||
    request.max_pages > 100 ||
    !Number.isInteger(request.max_opportunities) ||
    request.max_opportunities < 1 ||
    request.max_opportunities > 5000 ||
    !Number.isInteger(request.timeout_ms) ||
    request.timeout_ms < 1000 ||
    request.timeout_ms > 600000
  ) {
    throw new CollectorError(ERROR.denied);
  }
  const resourceHosts =
    typeof contract.browserHostsForSource === "function"
      ? contract.browserHostsForSource(source.hostname)
      : contract.browserHosts;
  if (!(resourceHosts instanceof Set) || !resourceHosts.has(source.hostname)) {
    throw new CollectorError(ERROR.denied);
  }
  return { ...request, source, contract, resourceHosts };
}

function resourceGuard(resourceHosts) {
  return async (route) => {
    const request = route.request();
    let target;
    try {
      target = new URL(request.url());
    } catch {
      await route.abort("blockedbyclient");
      return;
    }
    const permittedType = new Set([
      "document",
      "script",
      "stylesheet",
      "font",
      "image",
      "xhr",
      "fetch",
    ]);
    if (
      target.protocol !== "https:" ||
      !resourceHosts.has(target.hostname) ||
      !permittedType.has(request.resourceType())
    ) {
      await route.abort("blockedbyclient");
      return;
    }
    await route.continue();
  };
}

async function withBrowser(request, collect) {
  const chromiumBinary = process.env.KAJ_OPPORTUNITY_CHROMIUM_BINARY;
  if (
    typeof chromiumBinary !== "string" ||
    !path.isAbsolute(chromiumBinary) ||
    !fs.existsSync(chromiumBinary)
  ) {
    throw new CollectorError(ERROR.failed);
  }
  const browser = await chromium.launch({
    executablePath: chromiumBinary,
    chromiumSandbox: true,
    headless: true,
  });
  const timer = setTimeout(() => browser.close().catch(() => {}), request.timeout_ms);
  try {
    const context = await browser.newContext({
      locale: "zh-CN",
      extraHTTPHeaders: { "Accept-Language": "zh-CN,zh;q=0.9" },
      serviceWorkers: "block",
    });
    context.setDefaultTimeout(Math.min(30000, request.timeout_ms));
    await context.route("**/*", resourceGuard(request.resourceHosts));
    const page = await context.newPage();
    return await collect(page, context, request);
  } finally {
    clearTimeout(timer);
    await browser.close();
  }
}

function result(request, values) {
  const opportunities = Array.isArray(values.opportunities)
    ? values.opportunities
    : [];
  return {
    version: 1,
    collector: request.collector,
    complete: values.complete === true,
    pages_read: values.pagesRead,
    opportunities,
    category_labels: labels(opportunities.flatMap((row) => row.category_labels)),
    city_labels: labels(opportunities.flatMap((row) => row.city_labels)),
    cohort_labels: labels(opportunities.flatMap((row) => row.cohort_labels)),
    error_code: "",
  };
}

module.exports = {
  CollectorError,
  ERROR,
  assertObject,
  cohortLabels,
  labels,
  parseRequest,
  result,
  text,
  withBrowser,
};
