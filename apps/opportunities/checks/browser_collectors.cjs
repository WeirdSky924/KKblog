"use strict";

const {
  CollectorError,
  ERROR,
  assertObject,
  cohortLabels,
  labels,
  result,
  text,
  withBrowser,
} = require("./browser_runtime.cjs");

const HIRE_PLATFORM_BROWSER_HOSTS = new Set([
  "lf-package-cn.feishucdn.com",
  "lf3-atsx-byte.feishucdn.com",
  "lf3-cdn-tos.bytescm.com",
  "lf3-atsx-tob.feishucdn.com",
  "lf3-static.bytednsdoc.com",
]);

function hireContract(sourceHost, sourcePath) {
  return {
    sourceHost,
    sourcePath: (url) =>
      url.pathname.replace(/\/+$/u, "") === `/${sourcePath}`,
    browserHosts: new Set([sourceHost, ...HIRE_PLATFORM_BROWSER_HOSTS]),
  };
}

const CONTRACTS = Object.freeze({
  "hikvision-v1": {
    sourceHost: "campushr.hikvision.com",
    sourcePath: (url) =>
      url.pathname === "/school" && url.searchParams.get("schoolType") === "nozxf",
    browserHosts: new Set(["campushr.hikvision.com"]),
  },
  "xiaomi-campus-v1": hireContract(
    "xiaomi.jobs.f.mioffice.cn",
    "campus",
  ),
  "xiaomi-intern-v1": hireContract(
    "xiaomi.jobs.f.mioffice.cn",
    "internship",
  ),
  "bytedance-campus-v1": hireContract("jobs.bytedance.com", "campus/position"),
  "alibaba-campus-v1": {
    sourceHost: "campus-talent.alibaba.com",
    sourcePath: (url) =>
      url.pathname.replace(/\/+$/u, "") === "/campus/position" &&
      url.searchParams.get("batchId") === "100000760001",
    browserHosts: new Set([
      "campus-talent.alibaba.com",
      "fc.alibaba.com",
      "g.alicdn.com",
      "lang.alicdn.com",
    ]),
  },
});

async function waitForResponse(page, predicate, request) {
  return page.waitForResponse(predicate, { timeout: request.timeout_ms });
}

async function collectHikvision(request) {
  return withBrowser(request, async (page) => {
    const endpoint = "/api/search/crsPositionSearch/getPositionByQuery";
    await page.goto(request.source_url, { waitUntil: "domcontentloaded" });
    const pageSize = 100;
    let pageNumber = 1;
    let pagesRead = 0;
    let total = null;
    const opportunities = [];

    while (pagesRead < request.max_pages && opportunities.length < request.max_opportunities) {
      let payload;
      payload = await page.evaluate(
          async ({ endpoint, pageNumber, pageSize }) => {
            const body = new URLSearchParams({
              batchId: "",
              postAdSnList: "",
              interviewMethodList: "",
              keyWord: "",
              jobNature: "应届生",
              pageNum: String(pageNumber),
              pageSize: String(pageSize),
            });
            const response = await fetch(endpoint, {
              method: "POST",
              headers: { "content-type": "application/x-www-form-urlencoded" },
              body: body.toString(),
            });
            if (!response.ok) throw new Error("upstream");
            return response.json();
          },
        { endpoint, pageNumber, pageSize },
      );
      const pageData = assertObject(assertObject(payload).data);
      const rows = pageData.list;
      if (!Array.isArray(rows) || !Number.isInteger(pageData.total)) {
        throw new CollectorError(ERROR.upstream);
      }
      total = pageData.total;
      pagesRead += 1;
      for (const rowValue of rows) {
        const row = assertObject(rowValue);
        const id = text(row.id, 100);
        const title = text(row.postAdName, 200);
        if (!id || !title) throw new CollectorError(ERROR.upstream);
        const cities = labels(row.workPlaceList);
        opportunities.push({
          title,
          target_url: `${request.source.origin}/JobDetails.html?id=${encodeURIComponent(id)}&type=0&batchId=${encodeURIComponent(text(row.batchId, 100))}`,
          recruitment_type: "CAMPUS",
          plan: text(row.batchName, 200) || "校园招聘",
          location_text: cities.join("、") || "工作地点以官网为准",
          category_labels: labels([row.postAdSn, row.postStdSn]),
          city_labels: cities,
          cohort_labels: cohortLabels(row.batchName),
        });
        if (opportunities.length >= request.max_opportunities) break;
      }
      if (opportunities.length >= total || rows.length === 0) break;
      pageNumber += 1;
    }
    const complete = total !== null && opportunities.length >= total;
    return result(request, { complete, pagesRead, opportunities });
  });
}

function captureHireRequest(page, request) {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new CollectorError(ERROR.timeout)), request.timeout_ms);
    page.on("response", async (response) => {
      if (
        !response.url().includes("/api/v1/search/job/posts") ||
        response.status() !== 200
      ) return;
      try {
        const body = response.request().postDataJSON();
        const payload = await response.json();
        clearTimeout(timer);
        resolve({ response, body, payload });
      } catch {
        // Ignore the platform's initial unauthenticated 405/invalid response.
      }
    });
  });
}

function hireRow(request, row, websitePath, recruitmentType) {
  const id = text(row.id, 100);
  const title = text(row.title, 200);
  if (!id || !title) throw new CollectorError(ERROR.upstream);
  const cities = labels((row.city_list || []).map((value) => value?.name));
  const subject = text(
    row.job_subject?.name?.zh_cn || row.job_subject?.name?.i18n,
    200,
  );
  return {
    title,
    target_url: `${request.source.origin}/${websitePath}/position/${encodeURIComponent(id)}/detail`,
    recruitment_type: recruitmentType,
    plan: subject || (recruitmentType === "INTERNSHIP" ? "实习招聘" : "校园招聘"),
    location_text: cities.join("、") || "工作地点以官网为准",
    category_labels: labels([row.job_function?.name, row.job_category?.name]),
    city_labels: cities,
    cohort_labels: cohortLabels(subject, title),
  };
}

async function fetchHirePage(page, captured, body) {
  const url = new URL(captured.response.url());
  url.searchParams.set("limit", String(body.limit));
  url.searchParams.set("offset", String(body.offset));
  const headers = captured.response.request().headers();
  return page.evaluate(
    async ({ url, headers, body }) => {
      const response = await fetch(url, {
        method: "POST",
        headers: {
          "content-type": "application/json",
          "portal-channel": headers["portal-channel"],
          "portal-platform": "pc",
          "website-path": headers["website-path"],
          "x-csrf-token": headers["x-csrf-token"],
        },
        body: JSON.stringify(body),
      });
      if (!response.ok) throw new Error("upstream");
      return response.json();
    },
    { url: url.toString(), headers, body },
  );
}

async function collectHirePlatform(request, options) {
  return withBrowser(request, async (page) => {
    const capture = captureHireRequest(page, request);
    const filterResponse = options.bySubject
      ? waitForResponse(
          page,
          (response) =>
            response.url().includes("/api/v1/config/job/filters/3") &&
            response.status() === 200,
          request,
        )
      : null;
    await page.goto(request.source_url, { waitUntil: "domcontentloaded" });
    const captured = await capture;
    const initial = assertObject(assertObject(captured.payload).data);
    const subjectIds = options.bySubject
      ? loadHireSubjects(await (await filterResponse).json())
      : [null];
    const seen = new Set();
    const opportunities = [];
    let pagesRead = 0;
    let complete = true;

    for (const subjectId of subjectIds) {
      let offset = 0;
      let total = null;
      while (pagesRead < request.max_pages && opportunities.length < request.max_opportunities) {
        const body = {
          ...captured.body,
          limit: 100,
          offset,
          subject_id_list: subjectId ? [subjectId] : [],
        };
        const payload = offset === 0 && !subjectId ? captured.payload : await fetchHirePage(page, captured, body);
        const data = assertObject(assertObject(payload).data);
        const rows = data.job_post_list;
        if (!Array.isArray(rows) || !Number.isInteger(data.count)) {
          throw new CollectorError(ERROR.upstream);
        }
        total = data.count;
        pagesRead += 1;
        for (const rowValue of rows) {
          const row = assertObject(rowValue);
          const id = text(row.id, 100);
          if (seen.has(id)) continue;
          seen.add(id);
          opportunities.push(
            hireRow(
              request,
              row,
              options.websitePath,
              options.recruitmentType(row),
            ),
          );
          if (opportunities.length >= request.max_opportunities) break;
        }
        offset += rows.length;
        if (offset >= total || rows.length === 0) break;
      }
      if (total === null || offset < total) {
        complete = false;
        break;
      }
    }
    if (pagesRead < 1 || !Array.isArray(initial.job_post_list)) {
      throw new CollectorError(ERROR.upstream);
    }
    return result(request, { complete, pagesRead, opportunities });
  });
}

function loadHireSubjects(payload) {
  const subjects = assertObject(assertObject(payload).data).job_subject_list;
  if (!Array.isArray(subjects) || subjects.length < 1 || subjects.length > 20) {
    throw new CollectorError(ERROR.upstream);
  }
  return subjects.map((subject) => text(subject?.id, 100)).filter(Boolean);
}

function recruitmentFromHireRow(row) {
  const value = text(
    row.job_subject?.subject_group_info?.name ||
      row.recruit_type?.parent?.name ||
      row.recruit_type?.name,
    100,
  );
  return value.includes("实习") ? "INTERNSHIP" : "CAMPUS";
}

function collectXiaomi(request) {
  const internship = request.collector === "xiaomi-intern-v1";
  return collectHirePlatform(request, {
    bySubject: false,
    websitePath: internship ? "internship" : "campus",
    recruitmentType: () => (internship ? "INTERNSHIP" : "CAMPUS"),
  });
}

function collectByteDance(request) {
  return collectHirePlatform(request, {
    bySubject: true,
    websitePath: "campus",
    recruitmentType: recruitmentFromHireRow,
  });
}

function alibabaRow(request, row, plan) {
  const id =
    Number.isSafeInteger(row.id) && row.id > 0
      ? String(row.id)
      : /^\d{1,100}$/u.test(row.id || "")
        ? row.id
        : "";
  const title = text(row.name, 200);
  if (!id || !title) throw new CollectorError(ERROR.upstream);
  const cities = labels(
    Array.isArray(row.workLocations)
      ? row.workLocations.map((value) =>
          typeof value === "string" ? value : value?.name,
        )
      : [],
  );
  const category = text(row.categoryName || row.categoryType, 100);
  const effectivePlan = text(row.batchName, 200) || plan;
  return {
    title,
    target_url: `${request.source.origin}/campus/position/${encodeURIComponent(id)}?deptCodes=`,
    recruitment_type: /实习|intern/iu.test(effectivePlan) ? "INTERNSHIP" : "CAMPUS",
    plan: effectivePlan,
    location_text: cities.join("、") || "工作地点以官网为准",
    category_labels: labels([category]),
    city_labels: cities,
    cohort_labels: cohortLabels(effectivePlan),
  };
}

async function collectAlibaba(request) {
  return withBrowser(request, async (page) => {
    const firstResponse = waitForResponse(
      page,
      (response) => response.url().includes("/position/search?") && response.status() === 200,
      request,
    );
    await page.goto(request.source_url, { waitUntil: "domcontentloaded" });
    const captured = await firstResponse;
    const capturedBody = captured.request().postDataJSON();
    await captured.json();
    if (
      capturedBody.language !== "zh" ||
      capturedBody.channel !== "campus_group_official_site"
    ) {
      throw new CollectorError(ERROR.upstreamChannel);
    }
    const plan = "阿里巴巴2027届应届生";
    let total = null;
    const opportunities = [];
    let pageIndex = 1;
    let pagesRead = 0;
    while (pagesRead < request.max_pages && opportunities.length < request.max_opportunities) {
      const payload = await page.evaluate(
            async ({ url, body }) => {
              const response = await fetch(url, {
                method: "POST",
                headers: { "content-type": "application/json" },
                body: JSON.stringify(body),
              });
              if (!response.ok) throw new Error("upstream");
              return response.json();
            },
            {
              url: captured.url(),
              body: { ...capturedBody, pageIndex, pageSize: 100 },
            },
          );
      const data = assertObject(assertObject(payload).content);
      if (!Array.isArray(data.datas) || !Number.isInteger(data.totalCount)) {
        throw new CollectorError(ERROR.upstreamPaging);
      }
      total = data.totalCount;
      pagesRead += 1;
      for (const rowValue of data.datas) {
        try {
          opportunities.push(alibabaRow(request, assertObject(rowValue), plan));
        } catch {
          throw new CollectorError(ERROR.upstreamFields);
        }
        if (opportunities.length >= request.max_opportunities) break;
      }
      if (opportunities.length >= total || data.datas.length === 0) break;
      pageIndex += 1;
    }
    return result(request, {
      complete: total !== null && opportunities.length >= total,
      pagesRead,
      opportunities,
    });
  });
}

const COLLECTORS = Object.freeze({
  "hikvision-v1": collectHikvision,
  "xiaomi-campus-v1": collectXiaomi,
  "xiaomi-intern-v1": collectXiaomi,
  "bytedance-campus-v1": collectByteDance,
  "alibaba-campus-v1": collectAlibaba,
});

module.exports = { COLLECTORS, CONTRACTS };
