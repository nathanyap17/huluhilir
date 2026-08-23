import 'dart:convert';

import 'package:path/path.dart' as p;
import 'package:sqflite/sqflite.dart';

/// Offline capture queue. docs/DATA_MODEL.md § Phone-side (sqflite outbox).
///
/// NOT a full mirror of the server schema -- only what's needed to keep
/// capturing while offline: pending observations and buffered walk samples.
/// A farmer walking a hillside has no connectivity guarantee, and losing a
/// walk because the API was unreachable would be the worst possible failure.
class Outbox {
  Database? _db;

  Future<Database> get db async => _db ??= await _open();

  Future<Database> _open() async {
    final path = p.join(await getDatabasesPath(), 'huluhilir_outbox.db');
    return openDatabase(
      path,
      version: 1,
      onCreate: (db, _) async {
        await db.execute('''
          CREATE TABLE outbox_observations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            block_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            cycle_id TEXT,
            image_path TEXT NOT NULL,
            capture_target TEXT NOT NULL,
            captured_at TEXT NOT NULL,
            sync_status TEXT NOT NULL DEFAULT 'local_only'
          )
        ''');
        await db.execute('''
          CREATE TABLE outbox_walk_samples (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            walk_session_id TEXT NOT NULL,
            payload TEXT NOT NULL,
            sync_status TEXT NOT NULL DEFAULT 'local_only'
          )
        ''');
        await db.execute('''
          CREATE TABLE cached_farm_state (
            farm_id TEXT PRIMARY KEY,
            payload TEXT NOT NULL,
            cached_at TEXT NOT NULL
          )
        ''');
      },
    );
  }

  Future<void> queueObservation({
    required String blockId,
    required String userId,
    String? cycleId,
    required String imagePath,
    required String captureTarget,
  }) async {
    final database = await db;
    await database.insert('outbox_observations', {
      'block_id': blockId,
      'user_id': userId,
      'cycle_id': cycleId,
      'image_path': imagePath,
      'capture_target': captureTarget,
      'captured_at': DateTime.now().toIso8601String(),
    });
  }

  Future<List<Map<String, dynamic>>> pendingObservations() async {
    final database = await db;
    return database.query('outbox_observations', where: "sync_status = 'local_only'");
  }

  Future<void> markObservationSynced(int id) async {
    final database = await db;
    await database.update('outbox_observations', {'sync_status': 'synced'},
        where: 'id = ?', whereArgs: [id]);
  }

  Future<void> queueWalkSample(String walkSessionId, Map<String, dynamic> sample) async {
    final database = await db;
    await database.insert('outbox_walk_samples', {
      'walk_session_id': walkSessionId,
      'payload': jsonEncode(sample),
    });
  }

  Future<List<Map<String, dynamic>>> pendingWalkSamples(String walkSessionId) async {
    final database = await db;
    final rows = await database.query(
      'outbox_walk_samples',
      where: "walk_session_id = ? AND sync_status = 'local_only'",
      whereArgs: [walkSessionId],
    );
    return rows;
  }

  Future<void> markWalkSamplesSynced(List<int> ids) async {
    if (ids.isEmpty) return;
    final database = await db;
    final placeholders = List.filled(ids.length, '?').join(',');
    await database.rawUpdate(
      "UPDATE outbox_walk_samples SET sync_status = 'synced' WHERE id IN ($placeholders)",
      ids,
    );
  }

  Future<void> cacheFarmState(String farmId, Map<String, dynamic> payload) async {
    final database = await db;
    await database.insert(
      'cached_farm_state',
      {
        'farm_id': farmId,
        'payload': jsonEncode(payload),
        'cached_at': DateTime.now().toIso8601String(),
      },
      conflictAlgorithm: ConflictAlgorithm.replace,
    );
  }

  Future<Map<String, dynamic>?> cachedFarmState(String farmId) async {
    final database = await db;
    final rows =
        await database.query('cached_farm_state', where: 'farm_id = ?', whereArgs: [farmId]);
    if (rows.isEmpty) return null;
    return jsonDecode(rows.first['payload'] as String) as Map<String, dynamic>;
  }

  Future<int> pendingCount() async {
    final database = await db;
    final rows = await database.rawQuery(
        "SELECT COUNT(*) c FROM outbox_observations WHERE sync_status = 'local_only'");
    return (rows.first['c'] as int?) ?? 0;
  }
}
