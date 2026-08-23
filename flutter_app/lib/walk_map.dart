/// Live map for the walk: the GPS track so far, plus a marker per captured
/// block.
///
/// The point is orientation, not surveying — a farmer needs to see that the
/// app is actually following them and which corners of the garden are already
/// marked. It shows the walked path and marked points **only**; no boundary
/// is drawn, inferred, or stored, because a polygon around someone's plot is
/// exactly what huluhilir-rules §4 forbids on NCR land.
///
/// Tiles come from OpenStreetMap over the network. That makes this the one
/// part of the walk that degrades offline, so it is deliberately additive:
/// the track and markers still draw over an empty background, and nothing
/// about capturing a block depends on a tile ever arriving.
library;

import 'package:flutter/material.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:latlong2/latlong.dart';

import 'models.dart';
import 'theme.dart';

class WalkMap extends StatefulWidget {
  final List<LatLng> track;
  final List<BlockModel> blocks;
  final LatLng? current;
  final double height;

  const WalkMap({
    super.key,
    required this.track,
    required this.blocks,
    this.current,
    this.height = 260,
  });

  @override
  State<WalkMap> createState() => _WalkMapState();
}

class _WalkMapState extends State<WalkMap> {
  final _controller = MapController();
  bool _follow = true;

  @override
  void didUpdateWidget(covariant WalkMap oldWidget) {
    super.didUpdateWidget(oldWidget);
    // Recentre only while following. If the farmer has panned away to look at
    // something, yanking the camera back on every GPS tick would make the map
    // unusable.
    final here = widget.current;
    if (_follow && here != null && here != oldWidget.current) {
      _controller.move(here, _controller.camera.zoom);
    }
  }

  @override
  Widget build(BuildContext context) {
    final here = widget.current;
    final centre = here ??
        (widget.track.isNotEmpty ? widget.track.last : const LatLng(1.5533, 110.3592));

    return SizedBox(
      height: widget.height,
      child: ClipRRect(
        borderRadius: BorderRadius.circular(AppRadius.card),
        child: Stack(children: [
          FlutterMap(
            mapController: _controller,
            options: MapOptions(
              initialCenter: centre,
              initialZoom: 17,
              minZoom: 3,
              maxZoom: 19,
              // Any manual gesture stops the auto-follow, which is the
              // behaviour people expect from every navigation app.
              onPointerDown: (event, point) {
                if (_follow) setState(() => _follow = false);
              },
            ),
            children: [
              TileLayer(
                urlTemplate: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
                userAgentPackageName: 'my.huluhilir.app',
                // A missing tile must not throw: the walk continues over a
                // blank background rather than the map taking down the screen.
                errorTileCallback: (tile, error, stack) {},
              ),
              if (widget.track.length > 1)
                PolylineLayer(polylines: [
                  Polyline(
                    points: widget.track,
                    strokeWidth: 4,
                    color: AppColors.terracotta.withValues(alpha: 0.85),
                  ),
                ]),
              MarkerLayer(markers: [
                for (final b in widget.blocks)
                  Marker(
                    point: LatLng(b.lat, b.lon),
                    width: 34,
                    height: 34,
                    child: _BlockPin(rank: b.elevationRank),
                  ),
                if (here != null)
                  Marker(
                    point: here,
                    width: 22,
                    height: 22,
                    child: const _HerePin(),
                  ),
              ]),
            ],
          ),
          if (!_follow)
            Positioned(
              right: 10,
              bottom: 10,
              child: FloatingActionButton.small(
                heroTag: 'walkmap-recentre',
                backgroundColor: Colors.white,
                foregroundColor: AppColors.olive,
                onPressed: () {
                  setState(() => _follow = true);
                  if (here != null) _controller.move(here, 17);
                },
                child: const Icon(Icons.my_location, size: 18),
              ),
            ),
          // OSM's licence requires visible attribution wherever its tiles are
          // shown. This is not decoration and should not be removed.
          Positioned(
            left: 6,
            bottom: 4,
            child: Container(
              padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
              color: Colors.white70,
              child: Text('© OpenStreetMap',
                  style: AppText.sans(size: 9, color: AppColors.charcoal)),
            ),
          ),
        ]),
      ),
    );
  }
}

class _BlockPin extends StatelessWidget {
  final int rank;
  const _BlockPin({required this.rank});

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        color: AppColors.olive,
        shape: BoxShape.circle,
        border: Border.all(color: Colors.white, width: 2),
        boxShadow: softShadow(),
      ),
      alignment: Alignment.center,
      child: Text('$rank',
          style: AppText.sans(size: 12, weight: FontWeight.w700, color: Colors.white)),
    );
  }
}

class _HerePin extends StatelessWidget {
  const _HerePin();

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        color: AppColors.terracotta,
        shape: BoxShape.circle,
        border: Border.all(color: Colors.white, width: 3),
        boxShadow: softShadow(tint: AppColors.terracotta.withValues(alpha: 0.5)),
      ),
    );
  }
}
