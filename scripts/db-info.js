import { openDatabase } from '../src/db/database.js';

const db = openDatabase();
const summary = {
  projects: Number(db.prepare('SELECT COUNT(*) AS count FROM projects').get().count),
  phases: Number(db.prepare('SELECT COUNT(*) AS count FROM project_phases').get().count),
  docTypes: Number(db.prepare('SELECT COUNT(*) AS count FROM doc_types').get().count),
  constructionDocTypes: Number(db.prepare(`
    SELECT COUNT(*) AS count
    FROM doc_types dt
    JOIN project_phases pp ON pp.phase_id = dt.phase_id
    WHERE pp.phase_order = 5
  `).get().count),
  users: Number(db.prepare('SELECT COUNT(*) AS count FROM users').get().count),
  documents: Number(db.prepare('SELECT COUNT(*) AS count FROM documents').get().count),
};

console.log(JSON.stringify(summary, null, 2));
db.close();
