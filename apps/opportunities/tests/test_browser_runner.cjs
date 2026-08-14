"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");

const { CONTRACTS } = require("../checks/browser_collectors.cjs");
const {
  CollectorError,
  parseRequest,
  result,
} = require("../checks/browser_runtime.cjs");

function request(overrides = {}) {
  return {
    version: 1,
    collector: "hikvision-v1",
    source_url: "https://campushr.hikvision.com/school?schoolType=nozxf",
    allowed_hosts: ["campushr.hikvision.com"],
    max_pages: 10,
    max_opportunities: 500,
    timeout_ms: 60000,
    ...overrides,
  };
}

test("accepts only the fixed collector source contract", () => {
  const parsed = parseRequest(request({ max_pages: 100 }), CONTRACTS);

  assert.equal(parsed.source.hostname, "campushr.hikvision.com");
  assert.equal(parsed.contract.browserHosts.size, 1);
  assert.equal(parsed.max_pages, 100);
});

test("rejects administrator supplied hosts and unknown fields", () => {
  for (const value of [
    request({ allowed_hosts: ["jobs.example.com"] }),
    request({ max_pages: 101 }),
    { ...request(), selector: "body *" },
  ]) {
    assert.throws(
      () => parseRequest(value, CONTRACTS),
      (error) =>
        error instanceof CollectorError &&
        error.code === "opportunities.adapter_browser_denied.v1",
    );
  }
});

test("derives unique labels from collected public rows", () => {
  const parsed = parseRequest(request(), CONTRACTS);
  const output = result(parsed, {
    complete: true,
    pagesRead: 1,
    opportunities: [
      {
        category_labels: ["算法", "算法"],
        city_labels: ["杭州"],
        cohort_labels: ["2027届"],
      },
    ],
  });

  assert.deepEqual(output.category_labels, ["算法"]);
  assert.deepEqual(output.city_labels, ["杭州"]);
  assert.deepEqual(output.cohort_labels, ["2027届"]);
});
