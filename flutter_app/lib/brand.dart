/// Shared brand marks, so the logo is declared once rather than per screen.
library;

import 'package:flutter/material.dart';

/// The HuluHilir mark, shown to the right of the wordmark in page headers.
///
/// Falls back to an empty box rather than Flutter's broken-image glyph if the
/// asset is ever missing from a build — a header that is briefly missing its
/// logo is a cosmetic problem, and a red error box in the middle of the
/// farmer's dashboard is not.
class BrandLogo extends StatelessWidget {
  final double size;
  const BrandLogo({super.key, this.size = 40});

  @override
  Widget build(BuildContext context) {
    return Image.asset(
      'assets/brand/logo.png',
      height: size,
      fit: BoxFit.contain,
      filterQuality: FilterQuality.medium,
      errorBuilder: (context, error, stack) => SizedBox(height: size),
    );
  }
}

/// The mark sized and padded for an `AppBar.actions` slot, so every screen's
/// header carries it identically rather than each placing its own copy.
class BrandLogoAction extends StatelessWidget {
  const BrandLogoAction({super.key});

  @override
  Widget build(BuildContext context) {
    return const Padding(
      padding: EdgeInsets.only(right: 14),
      child: Center(child: BrandLogo(size: 30)),
    );
  }
}
