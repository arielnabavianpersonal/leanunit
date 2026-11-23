import { existsSync, readFileSync } from 'node:fs';
import { Session } from 'node:inspector/promises';
import path from 'node:path';
import { createInterface } from 'node:readline';
import { pathToFileURL } from 'node:url';

const EXTENSIONS = {
  typescript: ['.ts', '.mts', '.cts', '.js', '.mjs'],
  javascript: ['.js', '.mjs', '.cjs'],
};
const NOT_A_STATEMENT = /^(\/\/|\/\*|\*|\}|\)|\]|$)/;

class HarnessError extends Error {}

const parseOptions = (argv) => {
  const options = { sourceRoot: process.cwd(), language: 'javascript' };
  for (let index = 0; index < argv.length; index += 2) {
    if (argv[index] === '--source-root') options.sourceRoot = path.resolve(argv[index + 1]);
    if (argv[index] === '--language') options.language = argv[index + 1];
  }
  return options;
};

const options = parseOptions(process.argv.slice(2));
const protocol = process.stdout;
for (const method of ['log', 'info', 'debug', 'warn', 'error']) {
  console[method] = (...values) => process.stderr.write(`${values.map(String).join(' ')}\n`);
}

const moduleFile = (module) => {
  for (const extension of EXTENSIONS[options.language] ?? EXTENSIONS.javascript) {
    const candidate = path.join(options.sourceRoot, `${module}${extension}`);
    if (existsSync(candidate)) return candidate;
  }
  throw new HarnessError(`cannot find ${module}: no source file under ${options.sourceRoot}`);
};

const isClass = (value) => typeof value === 'function' && /^class[\s{]/.test(Function.prototype.toString.call(value));

const resolveTarget = async (name) => {
  const colon = name.indexOf(':');
  if (colon < 1) throw new HarnessError(`target ${name} must have the form module:Qualname`);
  const module = name.slice(0, colon);
  const parts = name.slice(colon + 1).split('.');
  const file = moduleFile(module);
  let exported;
  try {
    exported = await import(pathToFileURL(file).href);
  } catch (error) {
    throw new HarnessError(`cannot find ${name}: ${error}`);
  }
  if (parts.length === 1) {
    const fn = exported[parts[0]];
    if (typeof fn !== 'function' || isClass(fn)) throw new HarnessError(`${name} is not an exported function`);
    return { name, fn, owner: null, file, functionName: parts[0] };
  }
  if (parts.length === 2) {
    const owner = exported[parts[0]];
    if (!isClass(owner)) throw new HarnessError(`${parts[0]} is not an exported class`);
    const descriptor = Object.getOwnPropertyDescriptor(owner.prototype, parts[1]);
    if (!descriptor || typeof descriptor.value !== 'function') throw new HarnessError(`${name} is not a plain method`);
    return { name, fn: descriptor.value, owner, file, functionName: parts[1] };
  }
  throw new HarnessError(`${name} must name a function or a method of a class`);
};

const decodeReceiver = (owner, value) => {
  if (value === null || typeof value !== 'object' || Array.isArray(value)) {
    throw new HarnessError(`${owner.name} needs a JSON object, but got ${typeof value}`);
  }
  return Object.assign(Object.create(owner.prototype), structuredClone(value));
};

const encode = (value, seen = new WeakSet()) => {
  if (value === null || value === undefined) return null;
  if (typeof value === 'string' || typeof value === 'boolean') return value;
  if (typeof value === 'number') {
    if (!Number.isFinite(value)) throw new HarnessError('LeanUnit cannot encode a number that is not finite');
    return value;
  }
  if (typeof value !== 'object') throw new HarnessError(`LeanUnit cannot encode a value of type ${typeof value}`);
  if (seen.has(value)) throw new HarnessError('LeanUnit cannot encode a cyclic value');
  seen.add(value);
  if (Array.isArray(value)) return value.map((item) => encode(item, seen));
  if (value instanceof Set) return [...value].map((item) => encode(item, seen));
  if (value instanceof Date) return value.toISOString();
  if (value instanceof Map) {
    const entries = [...value.entries()];
    if (!entries.every(([key]) => typeof key === 'string')) {
      throw new HarnessError('LeanUnit can encode a Map only when its keys are strings');
    }
    return Object.fromEntries(entries.map(([key, item]) => [key, encode(item, seen)]));
  }
  return Object.fromEntries(
    Object.entries(value)
      .filter(([, item]) => typeof item !== 'function')
      .map(([key, item]) => [key, encode(item, seen)]),
  );
};

const errorName = (error) => (error && typeof error === 'object' && error.constructor?.name) || typeof error;

const call = async (target, args) => {
  let receiver = null;
  let rest = args;
  if (target.owner) {
    if (args.length === 0) throw new HarnessError(`${target.name} is a method, so its first argument must be the object`);
    receiver = decodeReceiver(target.owner, args[0]);
    rest = args.slice(1);
  }
  let result;
  try {
    result = target.fn.apply(receiver, structuredClone(rest));
    if (result && typeof result.then === 'function') result = await result;
  } catch (error) {
    return { raise: errorName(error), self: encode(receiver) };
  }
  return { self: encode(receiver), return: encode(result) };
};

const answer = async (request, targets) => {
  if (!targets.has(request.target)) {
    try {
      targets.set(request.target, await resolveTarget(request.target));
    } catch (error) {
      targets.set(request.target, error instanceof HarnessError ? error : new HarnessError(String(error)));
    }
  }
  const target = targets.get(request.target);
  if (target instanceof HarnessError) return { error: target.message };
  try {
    return await call(target, request.args);
  } catch (error) {
    return { error: error instanceof HarnessError ? error.message : String(error) };
  }
};

const lineStarts = (text) => {
  const starts = [0];
  for (let index = 0; index < text.length; index += 1) {
    if (text[index] === '\n') starts.push(index + 1);
  }
  return starts;
};

const lineOf = (starts, offset) => {
  let low = 0;
  let high = starts.length - 1;
  while (low < high) {
    const middle = Math.ceil((low + high) / 2);
    if (starts[middle] <= offset) low = middle;
    else high = middle - 1;
  }
  return low + 1;
};

const countAt = (ranges, offset) => {
  let best = null;
  for (const range of ranges) {
    if (range.startOffset <= offset && offset < range.endOffset) {
      if (!best || range.endOffset - range.startOffset < best.endOffset - best.startOffset) best = range;
    }
  }
  return best ? best.count : 0;
};

const functionLines = (text, starts, fn) => {
  const [whole] = fn.ranges;
  const lines = new Map();
  const first = lineOf(starts, whole.startOffset);
  const last = lineOf(starts, Math.max(whole.startOffset, whole.endOffset - 1));
  for (let line = first; line <= last; line += 1) {
    const begin = Math.max(starts[line - 1], whole.startOffset);
    const end = Math.min(line < starts.length ? starts[line] - 1 : text.length, whole.endOffset);
    const content = text.slice(begin, end);
    const offset = begin + (content.length - content.trimStart().length);
    if (NOT_A_STATEMENT.test(content.trim())) continue;
    lines.set(line, countAt(fn.ranges, offset) > 0);
  }
  return lines;
};

const coverageReport = async (session, targets) => {
  const { result } = await session.post('Profiler.takePreciseCoverage');
  const report = {};
  for (const target of targets.values()) {
    if (target instanceof HarnessError) continue;
    const script = result.find((entry) => entry.url === pathToFileURL(target.file).href);
    if (!script) {
      report[target.name] = { lines: 0, missing: [] };
      continue;
    }
    const text = readFileSync(target.file, 'utf8');
    const starts = lineStarts(text);
    const merged = new Map();
    for (const fn of script.functions.filter((entry) => entry.functionName === target.functionName && entry.ranges.length)) {
      for (const [line, hit] of functionLines(text, starts, fn)) merged.set(line, (merged.get(line) ?? false) || hit);
    }
    const missing = [...merged].filter(([, hit]) => !hit).map(([line]) => line).sort((a, b) => a - b);
    report[target.name] = { lines: merged.size, missing };
  }
  return report;
};

const main = async () => {
  const session = new Session();
  session.connect();
  await session.post('Profiler.enable');
  await session.post('Profiler.startPreciseCoverage', { callCount: true, detailed: true });
  const targets = new Map();
  for await (const line of createInterface({ input: process.stdin, crlfDelay: Infinity })) {
    if (!line.trim()) continue;
    protocol.write(`${JSON.stringify(await answer(JSON.parse(line), targets))}\n`);
  }
  const coverage = await coverageReport(session, targets);
  session.disconnect();
  protocol.write(`${JSON.stringify({ coverage })}\n`, () => process.exit(0));
};

main().catch((error) => {
  process.stderr.write(`${error?.stack ?? error}\n`);
  process.exit(1);
});
