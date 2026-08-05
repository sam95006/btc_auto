import 'package:flutter/material.dart';

import '../../app.dart';
import '../../data/dto/decision_dto.dart';
import '../widgets/common_widgets.dart';

class AccountScreen extends StatefulWidget {
  const AccountScreen({
    super.key,
    required this.onThemeMode,
    required this.onLocale,
  });

  final ValueChanged<ThemeMode> onThemeMode;
  final ValueChanged<Locale> onLocale;

  @override
  State<AccountScreen> createState() => _AccountScreenState();
}

class _AccountScreenState extends State<AccountScreen> {
  late Future<PublicAccountDto> _future;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    _future = NexusScope.of(context).repository.account();
  }

  @override
  Widget build(BuildContext context) {
    final a11y = NexusScope.of(context).a11y;
    return FutureBuilder<PublicAccountDto>(
      future: _future,
      builder: (context, snap) {
        if (snap.connectionState != ConnectionState.done) {
          return const Center(child: CircularProgressIndicator());
        }
        if (snap.hasError) {
          return EmptyState(message: '${snap.error}');
        }
        final a = snap.data!;
        return ListView(
          children: [
            ListTile(
              title: Text(a.displayName),
              subtitle: Text(a.emailMasked),
            ),
            const Divider(),
            ListTile(
              title: const Text('Theme'),
              subtitle: const Text('Adaptive system / light / dark'),
              trailing: DropdownButton<ThemeMode>(
                value: ThemeMode.system,
                items: const [
                  DropdownMenuItem(
                      value: ThemeMode.system, child: Text('System')),
                  DropdownMenuItem(
                      value: ThemeMode.light, child: Text('Light')),
                  DropdownMenuItem(value: ThemeMode.dark, child: Text('Dark')),
                ],
                onChanged: (v) {
                  if (v != null) widget.onThemeMode(v);
                },
              ),
            ),
            ListTile(
              title: const Text('Language'),
              trailing: DropdownButton<Locale>(
                value: const Locale('en'),
                items: const [
                  DropdownMenuItem(value: Locale('en'), child: Text('English')),
                  DropdownMenuItem(
                      value: Locale('zh', 'TW'), child: Text('繁體中文')),
                ],
                onChanged: (v) {
                  if (v != null) widget.onLocale(v);
                },
              ),
            ),
            SwitchListTile(
              title: const Text('Bold text'),
              value: a11y.boldText,
              onChanged: (v) => setState(() => a11y.boldText = v),
            ),
            ListTile(
              title: const Text('Text scale'),
              subtitle: Slider(
                value: a11y.textScale,
                min: 0.85,
                max: 2.0,
                onChanged: (v) => setState(() => a11y.setTextScale(v)),
              ),
            ),
          ],
        );
      },
    );
  }
}
