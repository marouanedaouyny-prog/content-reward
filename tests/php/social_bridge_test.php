<?php
declare(strict_types=1);

require __DIR__ . '/../../integrations/social-php/vendor/autoload.php';

use ContentReward\Social\Bridge;

function check(bool $condition, string $message): void {
    if (!$condition) { throw new RuntimeException($message); }
}

$calls = [];
$tokens = ['access_token' => 'synthetic-access', 'refresh_token' => 'synthetic-refresh',
           'expires_in' => 86400, 'scope' => 'user.info.basic', 'open_id' => 'synthetic-id'];
$bridge = new Bridge(static function ($method, $url, $headers, $body) use (&$calls, $tokens): array {
    $calls[] = [$method, $url, $headers, $body];
    if ($method === 'GET') {
        return [200, json_encode(['data' => ['user' => ['open_id' => 'synthetic-id', 'display_name' => 'Example']],
                                  'error' => ['code' => 'ok']])];
    }
    return [200, json_encode($tokens + ['debug' => 'must-not-escape'])];
});

$params = ['client_key' => 'synthetic-client', 'client_secret' => 'synthetic-secret',
           'redirect_uri' => 'http://127.0.0.1:8765/callback/', 'code' => 'synthetic-code',
           'code_verifier' => str_repeat('a', 64)];
$result = $bridge->dispatch(['protocol' => 1, 'action' => 'exchange', 'params' => $params]);
check($result === $tokens, 'Token response must be filtered');
[$method, $url, $headers, $body] = $calls[0];
parse_str($body, $form);
check($method === 'POST' && $url === 'https://open.tiktokapis.com/v2/oauth/token/', 'Fixed OAuth endpoint');
check(in_array('Content-Type: application/x-www-form-urlencoded', $headers, true), 'OAuth form content type');
check($form['code_verifier'] === $params['code_verifier'] && $form['code'] === 'synthetic-code', 'SDK code and PKCE');
check($form['grant_type'] === 'authorization_code' && $form['client_secret'] === 'synthetic-secret', 'SDK OAuth grant');

$bridge->dispatch(['protocol' => 1, 'action' => 'refresh', 'params' => $params + ['refresh_token' => 'synthetic-refresh']]);
parse_str($calls[1][3], $form);
check($form['grant_type'] === 'refresh_token' && $form['refresh_token'] === 'synthetic-refresh', 'SDK refresh grant');
check(!isset($form['code_verifier']), 'Refresh must not include code verifier');

$profile = $bridge->dispatch(['protocol' => 1, 'action' => 'profile', 'params' => ['access_token' => 'synthetic-access']]);
check($profile['open_id'] === 'synthetic-id', 'SDK user identity');
check(str_contains($calls[2][1], 'fields=open_id%2Cdisplay_name'), 'Basic profile fields');
check(!str_contains($calls[2][1], 'synthetic-access'), 'Token must not enter URL');
check(in_array('Authorization: Bearer synthetic-access', $calls[2][2], true), 'Bearer header');

foreach (['publish', 'upload', 'draft', 'custom_request'] as $action) {
    try {
        $bridge->dispatch(['protocol' => 1, 'action' => $action, 'params' => $params]);
        throw new LogicException('Disabled action succeeded');
    } catch (RuntimeException $e) { check($e->getMessage() === 'ACTION_DISABLED', 'Disabled action rejected'); }
}
check(count($calls) === 3, 'Rejected actions must not make network requests');

foreach ([[400, '{"error":"synthetic-secret"}'], [200, '{"error":{"code":"access_token_invalid"}}'],
          [302, '{"location":"https://example.com"}']] as $response) {
    $failed = new Bridge(static fn(...$args): array => $response);
    try {
        $failed->dispatch(['protocol' => 1, 'action' => 'refresh',
                          'params' => $params + ['refresh_token' => 'synthetic-refresh']]);
        throw new LogicException('Remote failure accepted');
    } catch (RuntimeException $e) { check($e->getMessage() === 'REMOTE_ERROR', 'Remote error must be sanitized'); }
}
echo "PASS: real SDK OAuth, refresh, profile and transport boundaries (offline)\n";
