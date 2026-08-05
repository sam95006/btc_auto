import 'package:flutter/material.dart';

import '../../app.dart';

class NexAiScreen extends StatefulWidget {
  const NexAiScreen({super.key});

  @override
  State<NexAiScreen> createState() => _NexAiScreenState();
}

class _NexAiScreenState extends State<NexAiScreen> {
  final _controller = TextEditingController();
  final _messages = <String>[];
  bool _busy = false;

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  Future<void> _send() async {
    final prompt = _controller.text.trim();
    if (prompt.isEmpty || _busy) return;
    final flags = NexusScope.of(context).flags;
    if (!flags.isEnabled('nex_ai_chat')) {
      setState(() => _messages.add('NEX AI disabled by feature flag'));
      return;
    }
    setState(() {
      _busy = true;
      _messages.add('You: $prompt');
      _controller.clear();
    });
    final reply = await NexusScope.of(context).repository.nexAiReply(prompt);
    if (!mounted) return;
    setState(() {
      _messages.add(reply);
      _busy = false;
    });
  }

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        Expanded(
          child: ListView.builder(
            padding: const EdgeInsets.all(16),
            itemCount: _messages.length,
            itemBuilder: (context, i) => Padding(
              padding: const EdgeInsets.only(bottom: 8),
              child: Text(_messages[i]),
            ),
          ),
        ),
        SafeArea(
          child: Padding(
            padding: const EdgeInsets.all(8),
            child: Row(
              children: [
                Expanded(
                  child: TextField(
                    controller: _controller,
                    decoration: const InputDecoration(
                      hintText: 'Ask about Decision context…',
                      border: OutlineInputBorder(),
                    ),
                    onSubmitted: (_) => _send(),
                  ),
                ),
                const SizedBox(width: 8),
                IconButton(
                  onPressed: _busy ? null : _send,
                  icon: const Icon(Icons.send),
                  tooltip: 'Send',
                ),
              ],
            ),
          ),
        ),
      ],
    );
  }
}
