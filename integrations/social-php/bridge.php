<?php
declare(strict_types=1);

// CLI only. Credentials travel through stdin; never through command arguments.
if (PHP_SAPI !== 'cli') { http_response_code(404); exit; }
ini_set('display_errors', '0');
ini_set('log_errors', '0');
try {
    require __DIR__ . '/vendor/autoload.php';
    $input = stream_get_contents(STDIN, 65537);
    if (strlen($input) > 65536) { throw new RuntimeException('INVALID_REQUEST'); }
    try { $request = json_decode($input, true, 16, JSON_THROW_ON_ERROR); }
    catch (JsonException) { throw new RuntimeException('INVALID_REQUEST'); }
    if (!is_array($request)) { throw new RuntimeException('INVALID_REQUEST'); }
    $result = (new ContentReward\Social\Bridge())->dispatch($request);
    echo json_encode(['protocol' => 1, 'ok' => true, 'data' => $result], JSON_THROW_ON_ERROR);
} catch (Throwable $error) {
    $code = in_array($error->getMessage(), ['INVALID_REQUEST', 'ACTION_DISABLED', 'REMOTE_ERROR', 'NETWORK_ERROR'], true)
        ? $error->getMessage() : 'BRIDGE_ERROR';
    echo json_encode(['protocol' => 1, 'ok' => false, 'error' => $code]);
    exit(1);
}
