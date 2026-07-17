import { readFile, stat } from 'node:fs/promises'
import { fileURLToPath } from 'node:url'

const assetsDir = fileURLToPath(new URL('../dist/assets/', import.meta.url))
const indexHtml = await readFile(fileURLToPath(new URL('../dist/index.html', import.meta.url)), 'utf8')
const entryMatches = [...indexHtml.matchAll(/<script\b[^>]*\btype=["']module["'][^>]*\bsrc=["']\/assets\/([^"']+\.js)["']/gi)]
const entryFiles = [...new Set(entryMatches.map(match => match[1]))]

if (entryFiles.length !== 1) {
  throw new Error(`Expected one entry bundle, found: ${entryFiles.join(', ') || 'none'}`)
}

const entry = entryFiles[0]
const bytes = (await stat(`${assetsDir}/${entry}`)).size
const budget = 300 * 1024

if (bytes > budget) {
  throw new Error(`Entry bundle ${entry} is ${bytes} bytes; budget is ${budget} bytes`)
}

console.log(JSON.stringify({ entry, bytes, budget, passed: true }))
