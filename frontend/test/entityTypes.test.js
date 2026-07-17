import test from 'node:test'
import assert from 'node:assert/strict'

import {
  colorForEntityType,
  entityTypeKey,
  groupEntityTypes,
} from '../src/utils/entityTypes.js'

const COLORS = ['orange', 'blue', 'green']

test('groups mixed-case persisted entity types under the first display label', () => {
  const groups = groupEntityTypes([
    { type: 'concept' },
    { type: 'Concept' },
    { type: ' CONCEPT ' },
    { type: 'Person' },
  ], COLORS)

  assert.deepEqual(groups, [
    { key: 'concept', name: 'concept', color: 'orange' },
    { key: 'person', name: 'Person', color: 'blue' },
  ])
  assert.equal(colorForEntityType('Concept', groups), 'orange')
  assert.equal(colorForEntityType(' CONCEPT ', groups), 'orange')
})

test('normalizes whitespace and common Unicode case folds', () => {
  assert.equal(entityTypeKey('  Data\t  Model '), 'data model')
  assert.equal(entityTypeKey('Straße'), entityTypeKey('STRASSE'))
  assert.equal(entityTypeKey('ΟΣ'), entityTypeKey('ος'))
})
