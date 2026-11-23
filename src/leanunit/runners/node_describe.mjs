import { existsSync } from 'node:fs';
import { createRequire } from 'node:module';
import path from 'node:path';

const EXTENSIONS = {
  typescript: ['.ts', '.mts', '.cts', '.js', '.mjs'],
  javascript: ['.js', '.mjs', '.cjs'],
};
const OPAQUE_OBJECTS = new Set(['Map', 'Set', 'Date', 'Promise', 'RegExp', 'Function', 'WeakMap', 'WeakSet']);

class DescribeError extends Error {}

const parseOptions = (argv) => {
  const options = { sourceRoot: process.cwd(), language: 'typescript', mode: null, target: null };
  for (let index = 0; index < argv.length; index += 1) {
    const flag = argv[index];
    if (flag === '--source-root') options.sourceRoot = path.resolve(argv[(index += 1)]);
    else if (flag === '--language') options.language = argv[(index += 1)];
    else if (flag === '--describe' || flag === '--methods') {
      options.mode = flag.slice(2);
      options.target = argv[(index += 1)];
    }
  }
  return options;
};

const loadTypeScript = (sourceRoot) => {
  const places = [
    process.env.LEANUNIT_TYPESCRIPT,
    path.join(sourceRoot, 'package.json'),
    path.join(process.cwd(), 'package.json'),
  ].filter(Boolean);
  for (const place of places) {
    try {
      const require = createRequire(place.endsWith('.json') ? place : path.join(place, 'package.json'));
      return place.endsWith('.json') ? require('typescript') : require(place);
    } catch {
      continue;
    }
  }
  throw new DescribeError(
    'LeanUnit needs the typescript package to describe TypeScript or JavaScript. ' +
      'Install it in the project, or set LEANUNIT_TYPESCRIPT to its folder.',
  );
};

const moduleFile = (options, module) => {
  for (const extension of EXTENSIONS[options.language] ?? EXTENSIONS.typescript) {
    const candidate = path.join(options.sourceRoot, `${module}${extension}`);
    if (existsSync(candidate)) return candidate;
  }
  throw new DescribeError(`cannot find ${module}: no source file under ${options.sourceRoot}`);
};

const describe = (ts, options) => {
  const colon = options.target.indexOf(':');
  if (colon < 1) throw new DescribeError(`target ${options.target} must have the form module:Qualname`);
  const module = options.target.slice(0, colon);
  const parts = options.target.slice(colon + 1).split('.');
  const file = moduleFile(options, module);
  const program = ts.createProgram([file], {
    allowJs: true,
    checkJs: false,
    strict: true,
    noEmit: true,
    skipLibCheck: true,
    allowImportingTsExtensions: true,
    target: ts.ScriptTarget.ES2022,
    module: ts.ModuleKind.NodeNext,
    moduleResolution: ts.ModuleResolutionKind.NodeNext,
  });
  const checker = program.getTypeChecker();
  const source = program.getSourceFile(file);
  const moduleSymbol = source && checker.getSymbolAtLocation(source);
  const exportsOf = moduleSymbol ? checker.getExportsOfModule(moduleSymbol) : [];
  const exported = (name) => {
    const symbol = exportsOf.find((candidate) => candidate.getName() === name);
    if (!symbol) throw new DescribeError(`cannot find ${options.target}: ${name} is not exported`);
    return symbol.flags & ts.SymbolFlags.Alias ? checker.getAliasedSymbol(symbol) : symbol;
  };
  const types = {};
  let anonymous = 0;

  const isNullish = (type) => (type.flags & (ts.TypeFlags.Null | ts.TypeFlags.Undefined | ts.TypeFlags.Void)) !== 0;
  const record = (type) => {
    const symbol = type.aliasSymbol ?? type.getSymbol();
    let name = symbol?.getName();
    if (!name || name.startsWith('__')) name = `Shape${(anonymous += 1)}`;
    if (types[name]) return { kind: 'dataclass', name };
    types[name] = { fields: [] };
    types[name].fields = fieldsOf(type);
    return { kind: 'dataclass', name };
  };
  const tree = (type) => {
    const flags = type.flags;
    if (flags & (ts.TypeFlags.Any | ts.TypeFlags.Unknown)) return { kind: 'any' };
    if (flags & ts.TypeFlags.StringLike) return { kind: 'str' };
    if (flags & ts.TypeFlags.NumberLike) return { kind: 'int' };
    if (flags & ts.TypeFlags.BooleanLike) return { kind: 'bool' };
    if (isNullish(type)) return { kind: 'none' };
    if (type.isUnion()) {
      const present = type.types.filter((member) => !isNullish(member));
      const optional = present.length < type.types.length;
      let inner = { kind: 'any' };
      if (present.every((member) => member.flags & ts.TypeFlags.BooleanLike)) inner = { kind: 'bool' };
      else if (present.every((member) => member.flags & ts.TypeFlags.StringLike)) inner = { kind: 'str' };
      else if (present.every((member) => member.flags & ts.TypeFlags.NumberLike)) inner = { kind: 'int' };
      else if (present.length === 1) inner = tree(present[0]);
      return optional ? { kind: 'optional', item: inner } : inner;
    }
    if (checker.isArrayType(type)) {
      const [item] = checker.getTypeArguments(type);
      return { kind: 'list', item: item ? tree(item) : { kind: 'any' } };
    }
    if (checker.isTupleType(type) || type.getCallSignatures().length) return { kind: 'any' };
    const symbolName = (type.aliasSymbol ?? type.getSymbol())?.getName();
    if (symbolName && OPAQUE_OBJECTS.has(symbolName)) return { kind: 'any' };
    const stringIndex = checker.getIndexInfoOfType(type, ts.IndexKind.String);
    if (stringIndex && checker.getPropertiesOfType(type).length === 0) return { kind: 'dict', value: tree(stringIndex.type) };
    if (flags & ts.TypeFlags.Object) return record(type);
    return { kind: 'any' };
  };
  const fieldsOf = (type) =>
    checker
      .getPropertiesOfType(type)
      .filter((property) => !property.getName().startsWith('#'))
      .filter((property) => !(property.flags & (ts.SymbolFlags.Method | ts.SymbolFlags.GetAccessor | ts.SymbolFlags.SetAccessor)))
      .map((property) => {
        const declaration = property.valueDeclaration ?? property.declarations?.[0] ?? source;
        return { name: property.getName(), type: tree(checker.getTypeOfSymbolAtLocation(property, declaration)) };
      })
      .filter((field) => !(field.type.kind === 'any' && isFunctionField(type, field.name)));
  const isFunctionField = (type, name) => {
    const property = type.getProperty(name);
    const declaration = property?.valueDeclaration;
    return declaration ? checker.getTypeOfSymbolAtLocation(property, declaration).getCallSignatures().length > 0 : false;
  };
  const describeSignature = (target, name, symbol, declaration) => {
    const signature = checker.getTypeOfSymbolAtLocation(symbol, declaration).getCallSignatures()[0];
    if (!signature) throw new DescribeError(`${target} is not callable`);
    const params = signature.getParameters().map((parameter) => {
      const parameterDeclaration = parameter.valueDeclaration ?? declaration;
      if (parameterDeclaration && ts.isParameter(parameterDeclaration) && parameterDeclaration.dotDotDotToken) {
        throw new DescribeError(`${target} has a rest parameter, so it takes a variable number of arguments`);
      }
      return { name: parameter.getName(), type: tree(checker.getTypeOfSymbolAtLocation(parameter, parameterDeclaration)) };
    });
    const returned = signature.getReturnType();
    const awaited = checker.getAwaitedType ? checker.getAwaitedType(returned) ?? returned : returned;
    return { target, name, params, returns: tree(awaited) };
  };
  const methodsOfClass = (classSymbol) => {
    const declaration = classSymbol.declarations?.find((item) => ts.isClassDeclaration(item) || ts.isClassExpression(item));
    if (!declaration) return [];
    return declaration.members.filter(
      (member) =>
        ts.isMethodDeclaration(member) &&
        member.body &&
        member.name &&
        ts.isIdentifier(member.name) &&
        !(ts.getCombinedModifierFlags(member) & ts.ModifierFlags.Static),
    );
  };

  if (parts.length === 1) {
    const symbol = exported(parts[0]);
    if (symbol.flags & ts.SymbolFlags.Class) {
      const methods = methodsOfClass(symbol);
      const owner = record(checker.getDeclaredTypeOfSymbol(symbol));
      const functions = methods.map((member) => {
        const methodSymbol = checker.getSymbolAtLocation(member.name);
        return describeSignature(`${options.target}.${member.name.text}`, member.name.text, methodSymbol, member);
      });
      return { target: options.target, owner, functions, types, methods: functions.map((fn) => fn.target) };
    }
    const declaration = symbol.valueDeclaration ?? symbol.declarations?.[0];
    const described = describeSignature(options.target, parts[0], symbol, declaration);
    return { target: options.target, owner: null, functions: [described], types, methods: [options.target] };
  }
  if (parts.length === 2) {
    const classSymbol = exported(parts[0]);
    const member = methodsOfClass(classSymbol).find((item) => item.name.text === parts[1]);
    if (!member) throw new DescribeError(`${options.target} is not a plain method of ${parts[0]}`);
    const owner = record(checker.getDeclaredTypeOfSymbol(classSymbol));
    const described = describeSignature(options.target, parts[1], checker.getSymbolAtLocation(member.name), member);
    return { target: options.target, owner, functions: [described], types, methods: [options.target] };
  }
  throw new DescribeError(`${options.target} must name a function, a class, or a method of a class`);
};

const main = () => {
  const options = parseOptions(process.argv.slice(2));
  try {
    if (!options.target) throw new DescribeError('use --describe module:Qualname or --methods module:Qualname');
    const description = describe(loadTypeScript(options.sourceRoot), options);
    const answer = options.mode === 'methods' ? { methods: description.methods } : description;
    process.stdout.write(`${JSON.stringify(answer)}\n`);
  } catch (error) {
    const message = error instanceof DescribeError ? error.message : String(error?.stack ?? error);
    process.stdout.write(`${JSON.stringify({ error: message })}\n`);
  }
};

main();
