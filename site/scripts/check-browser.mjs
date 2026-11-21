// Browser smoke and accessibility checks against a running preview server.
//   npm run build && npx vite preview --port 4173 &  then  npm run check:browser
// Writes screenshots to site/qa/ (git-ignored). Exits non-zero on failures.
import { mkdirSync } from "node:fs";
import AxeBuilder from "@axe-core/playwright";
import { chromium } from "playwright";

const BASE = process.env.SITE_URL ?? "http://localhost:4173/";
const OUT = new URL("../qa/", import.meta.url).pathname;
mkdirSync(OUT, { recursive: true });

const failures = [];
const fail = (m) => {
  failures.push(m);
  console.error("FAIL", m);
};

const browser = await chromium.launch({ args: ["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"] });

async function run(name, viewport, opts = {}) {
  const ctx = await browser.newContext({
    viewport,
    deviceScaleFactor: opts.dpr ?? 1,
    isMobile: !!opts.mobile,
    hasTouch: !!opts.mobile,
    reducedMotion: opts.reducedMotion ? "reduce" : "no-preference",
  });
  const page = await ctx.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  page.on("console", (m) => m.type() === "error" && errors.push(m.text()));
  await page.goto(BASE, { waitUntil: "networkidle" });
  await page.waitForTimeout(1500);

  const chapters = await page.$$eval("[data-chapter]", (els) => els.length);
  for (let i = 0; i < chapters; i++) {
    await page.$eval(`[data-chapter="${i}"]`, (el) => {
      const r = el.getBoundingClientRect();
      // Phones read below the pinned pitch; desktop reads mid-screen.
      const y = window.innerWidth < 1000 ? r.top - 0.66 * window.innerHeight : r.top + r.height / 2 - window.innerHeight / 2;
      window.scrollTo(0, window.scrollY + y);
    });
    await page.waitForTimeout(opts.reducedMotion ? 300 : 1600);
    await page.screenshot({ path: `${OUT}${name}-ch${i}.png` });
  }
  // Interaction checks on the information-boundary chapter.
  await page.$eval('[data-chapter="3"]', (el) => {
    const r = el.getBoundingClientRect();
    const y = window.innerWidth < 1000 ? r.top - 0.66 * window.innerHeight : r.top + r.height / 2 - window.innerHeight / 2;
    window.scrollTo(0, window.scrollY + y);
  });
  await page.waitForTimeout(600);
  const checked = () => page.$eval('[aria-label="Information available to the model"] [aria-checked="true"]', (b) => b.textContent);
  if (!(await checked()).includes("future_ball")) fail(`${name}: scrolling to chapter 3 did not select future_ball`);
  const opp = page.locator('[aria-label="Information available to the model"] button').nth(2);
  if (opts.mobile) await opp.tap();
  else {
    await opp.focus();
    await page.keyboard.press("Enter");
  }
  if (!(await checked()).includes("future_opponent_plus_ball")) fail(`${name}: regime switch failed`);
  const range = page.locator('input[type="range"]');
  await range.focus();
  for (let k = 0; k < 20; k++) await page.keyboard.press("ArrowLeft");
  const vt = await range.getAttribute("aria-valuetext");
  if (!vt?.includes("t − 1.0 s")) fail(`${name}: keyboard scrubbing gave "${vt}"`);
  if (!opts.reducedMotion) {
    await page.getByRole("button", { name: "2D view" }).click();
    if (!(await page.$(".pitch-svg"))) fail(`${name}: 2D fallback did not render`);
    await page.getByRole("button", { name: "3D view" }).click();
  } else if (!(await page.$(".pitch-svg"))) fail(`${name}: reduced motion should start in the 2D fallback`);
  await page.screenshot({ path: `${OUT}${name}-interaction.png` });

  for (const id of ["design", "results", "limits", "research"]) {
    await page.$eval(`#${id}`, (el) => el.scrollIntoView({ behavior: "instant" }));
    await page.waitForTimeout(300);
    await page.screenshot({ path: `${OUT}${name}-${id}.png` });
  }

  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  if (overflow > 1) fail(`${name}: horizontal overflow ${overflow}px`);

  const axe = await new AxeBuilder({ page }).disableRules(["region"]).analyze();
  for (const v of axe.violations) {
    if (v.impact === "serious" || v.impact === "critical") fail(`${name}: axe ${v.id} (${v.nodes.length}) ${v.nodes[0]?.target}`);
  }
  for (const e of errors) fail(`${name}: console ${e}`);
  await ctx.close();
}

await run("desktop", { width: 1440, height: 900 });
await run("mobile", { width: 390, height: 844 }, { mobile: true, dpr: 2 });
await run("reduced", { width: 1280, height: 800 }, { reducedMotion: true });
await browser.close();

if (failures.length) {
  console.error(`${failures.length} browser check failure(s)`);
  process.exit(1);
}
console.log("browser checks passed");
