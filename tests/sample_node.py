SAMPLE_JS = """export class Box {
  constructor() {
    this.items = {};
    this.count = 0;
  }

  add(key, value) {
    if (key in this.items) {
      throw new RangeError(key);
    }
    this.items[key] = { name: key, value };
    this.count += 1;
    return this.count;
  }

  async rename(key, next) {
    this.items[next] = { ...this.items[key], name: next };
    delete this.items[key];
    return next;
  }

  noisy() {
    console.log('hello from the code');
  }

  callback() {
    return () => 1;
  }
}

export function double(n) {
  if (n < 0) {
    return 0;
  }
  return n * 2;
}
"""

SAMPLE_TS = """export interface Item {
  name: string;
  value: unknown;
}

export class Box {
  items: Record<string, Item>;
  count: number;
  label?: string;

  constructor() {
    this.items = {};
    this.count = 0;
  }

  add(key: string, value: unknown): number {
    if (key in this.items) {
      throw new RangeError(key);
    }
    this.items[key] = { name: key, value };
    this.count += 1;
    return this.count;
  }

  async names(prefix: string): Promise<string[]> {
    return Object.keys(this.items).filter((name) => name.startsWith(prefix));
  }

  static make(): Box {
    return new Box();
  }
}

export function double(n: number): number {
  if (n < 0) {
    return 0;
  }
  return n * 2;
}

export function total(...values: number[]): number {
  return values.reduce((sum, value) => sum + value, 0);
}
"""


def write_node_samples(root):
    (root / "box.mjs").write_text(SAMPLE_JS)
    (root / "typed.ts").write_text(SAMPLE_TS)
    return root
