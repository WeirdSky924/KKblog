"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");

const {
  CONTRACTS,
  hireRow,
  recruitmentFromHireRow,
} = require("../checks/browser_collectors.cjs");
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

test("accepts an allowlisted Feishu tenant list page", () => {
  const parsed = parseRequest(
    request({
      collector: "feishu-career-v1",
      source_url: "https://fastbase.jobs.feishu.cn/588906/position/list",
      allowed_hosts: ["fastbase.jobs.feishu.cn"],
    }),
    CONTRACTS,
  );

  assert.equal(parsed.source.hostname, "fastbase.jobs.feishu.cn");
  assert(parsed.resourceHosts.has("fastbase.jobs.feishu.cn"));
  assert(parsed.resourceHosts.has("lf-package-cn.feishucdn.com"));
});

test("rejects Feishu detail pages and cross-tenant hosts", () => {
  for (const value of [
    request({
      collector: "feishu-career-v1",
      source_url:
        "https://fastbase.jobs.feishu.cn/588906/position/123/detail",
      allowed_hosts: ["fastbase.jobs.feishu.cn"],
    }),
    request({
      collector: "feishu-career-v1",
      source_url: "https://unknown.jobs.feishu.cn/position/list",
      allowed_hosts: ["unknown.jobs.feishu.cn"],
    }),
  ]) {
    assert.throws(
      () => parseRequest(value, CONTRACTS),
      (error) =>
        error instanceof CollectorError &&
        error.code === "opportunities.adapter_browser_denied.v1",
    );
  }
});

test("maps a specific Feishu internship type before its social parent", () => {
  const row = {
    id: "7678914324601571638",
    title: "国际化出海HRBP-招聘方向",
    recruit_type: {
      name: "实习",
      parent: { name: "社招" },
    },
  };

  assert.equal(recruitmentFromHireRow(row), "INTERNSHIP");
  assert.equal(
    hireRow(
      { source: new URL("https://k11pnjpvz1.jobs.feishu.cn/index") },
      row,
      "position",
      recruitmentFromHireRow(row),
    ).plan,
    "实习招聘",
  );
});

test("accepts the nested public Feishu position list path", () => {
  const parsed = parseRequest(
    request({
      collector: "feishu-career-v1",
      source_url: "https://tarsrobot.jobs.feishu.cn/index/position/list",
      allowed_hosts: ["tarsrobot.jobs.feishu.cn"],
    }),
    CONTRACTS,
  );

  assert.equal(parsed.source.pathname, "/index/position/list");
});

test("accepts a single prefixed Feishu position list path", () => {
  const parsed = parseRequest(
    request({
      collector: "feishu-career-v1",
      source_url:
        "https://smartlogictech.jobs.feishu.cn/xiaozhao/position/list",
      allowed_hosts: ["smartlogictech.jobs.feishu.cn"],
    }),
    CONTRACTS,
  );

  assert.equal(parsed.source.pathname, "/xiaozhao/position/list");
});

test("accepts a verified Feishu tenant nested list", () => {
  const parsed = parseRequest(
    request({
      collector: "feishu-career-v1",
      source_url: "https://dexmal-inc.jobs.feishu.cn/index/position/list",
      allowed_hosts: ["dexmal-inc.jobs.feishu.cn"],
    }),
    CONTRACTS,
  );

  assert.equal(parsed.source.hostname, "dexmal-inc.jobs.feishu.cn");
});

test("accepts the verified Sentury Feishu tenant list", () => {
  const parsed = parseRequest(
    request({
      collector: "feishu-career-v1",
      source_url: "https://senturytire.jobs.feishu.cn/029966/position/list",
      allowed_hosts: ["senturytire.jobs.feishu.cn"],
    }),
    CONTRACTS,
  );

  assert.equal(parsed.source.hostname, "senturytire.jobs.feishu.cn");
});

test("accepts the verified Xpeng Feishu tenant list", () => {
  const parsed = parseRequest(
    request({
      collector: "feishu-career-v1",
      source_url: "https://xiaopeng.jobs.feishu.cn/campus/position/list",
      allowed_hosts: ["xiaopeng.jobs.feishu.cn"],
    }),
    CONTRACTS,
  );

  assert.equal(parsed.source.hostname, "xiaopeng.jobs.feishu.cn");
});

test("accepts the verified Qunar Feishu tenant list", () => {
  const parsed = parseRequest(
    request({
      collector: "feishu-career-v1",
      source_url: "https://hf7l9aiqzx.jobs.feishu.cn/index/position/list",
      allowed_hosts: ["hf7l9aiqzx.jobs.feishu.cn"],
    }),
    CONTRACTS,
  );

  assert.equal(parsed.source.hostname, "hf7l9aiqzx.jobs.feishu.cn");
});

test("accepts the verified Radrock Feishu tenant list", () => {
  const parsed = parseRequest(
    request({
      collector: "feishu-career-v1",
      source_url: "https://radrocktech.jobs.feishu.cn/index/position/list",
      allowed_hosts: ["radrocktech.jobs.feishu.cn"],
    }),
    CONTRACTS,
  );

  assert.equal(parsed.source.hostname, "radrocktech.jobs.feishu.cn");
});

test("accepts both verified Weikezhijia Feishu list paths", () => {
  for (const source_url of [
    "https://weikezhijia.jobs.feishu.cn/MSXF/position/list",
    "https://weikezhijia.jobs.feishu.cn/MSXF0619/position/list",
  ]) {
    const parsed = parseRequest(
      request({
        collector: "feishu-career-v1",
        source_url,
        allowed_hosts: ["weikezhijia.jobs.feishu.cn"],
      }),
      CONTRACTS,
    );
    assert.equal(parsed.source.hostname, "weikezhijia.jobs.feishu.cn");
  }
});

test("accepts the verified Fanuc Feishu social list", () => {
  const parsed = parseRequest(
    request({
      collector: "feishu-career-v1",
      source_url: "https://iwhih7is28.jobs.feishu.cn/index",
      allowed_hosts: ["iwhih7is28.jobs.feishu.cn"],
    }),
    CONTRACTS,
  );

  assert.equal(parsed.source.hostname, "iwhih7is28.jobs.feishu.cn");
});

test("accepts the verified Leiniao Feishu list", () => {
  const parsed = parseRequest(
    request({
      collector: "feishu-career-v1",
      source_url: "https://leiniao-ibg.jobs.feishu.cn/index",
      allowed_hosts: ["leiniao-ibg.jobs.feishu.cn"],
    }),
    CONTRACTS,
  );

  assert.equal(parsed.source.hostname, "leiniao-ibg.jobs.feishu.cn");
});

test("accepts the verified Anker Feishu list", () => {
  const parsed = parseRequest(
    request({
      collector: "feishu-career-v1",
      source_url:
        "https://anker-in.jobs.feishu.cn/campushirecn/position/list",
      allowed_hosts: ["anker-in.jobs.feishu.cn"],
    }),
    CONTRACTS,
  );

  assert.equal(parsed.source.hostname, "anker-in.jobs.feishu.cn");
});

test("accepts both verified Hesai Feishu list paths", () => {
  for (const source_url of [
    "https://kwh0jtf778.jobs.feishu.cn/229043/position/list",
    "https://kwh0jtf778.jobs.feishu.cn/index/position/list",
  ]) {
    const parsed = parseRequest(
      request({
        collector: "feishu-career-v1",
        source_url,
        allowed_hosts: ["kwh0jtf778.jobs.feishu.cn"],
      }),
      CONTRACTS,
    );
    assert.equal(parsed.source.hostname, "kwh0jtf778.jobs.feishu.cn");
  }
});

test("accepts both canonical LeoGlobal Feishu list paths", () => {
  for (const source_url of [
    "https://leoglobal.jobs.feishu.cn/leosz/position/list",
    "https://leoglobal.jobs.feishu.cn/leoxz/position/list",
  ]) {
    const parsed = parseRequest(
      request({
        collector: "feishu-career-v1",
        source_url,
        allowed_hosts: ["leoglobal.jobs.feishu.cn"],
      }),
      CONTRACTS,
    );
    assert.equal(parsed.source.hostname, "leoglobal.jobs.feishu.cn");
  }
});
