<?php
declare(strict_types=1);

namespace ContentReward\Social;

use Closure;
use Composer\InstalledVersions;
use RuntimeException;
use TikTok\Authentication\Authentication;
use TikTok\User\User;

/** A small allowlisted transport; SDK debug objects and token URLs never leave it. */
final class Http
{
    public function __construct(private ?Closure $sender = null) {}

    public function send(string $method, string $endpoint, array $params, string $token = ''): array
    {
        if (!(($method === 'POST' && $endpoint === '/oauth/token/') ||
              ($method === 'GET' && $endpoint === '/user/info/'))) {
            throw new RuntimeException('ACTION_DISABLED');
        }
        $url = 'https://open.tiktokapis.com/v2' . $endpoint;
        $headers = ['Accept: application/json'];
        $body = null;
        unset($params['access_token']);
        if ($method === 'POST') {
            $headers[] = 'Content-Type: application/x-www-form-urlencoded';
            $body = http_build_query($params, '', '&', PHP_QUERY_RFC3986);
        } else {
            if ($token === '' || preg_match('/[\x00-\x20\x7f]/', $token)) {
                throw new RuntimeException('INVALID_REQUEST');
            }
            $headers[] = 'Authorization: Bearer ' . $token;
            $url .= '?' . http_build_query($params, '', '&', PHP_QUERY_RFC3986);
        }
        $sender = $this->sender ?? self::curl(...);
        [$status, $raw] = $sender($method, $url, $headers, $body);
        if (strlen($raw) > 1048576) {
            throw new RuntimeException('REMOTE_ERROR');
        }
        $data = json_decode($raw, true, 32, JSON_THROW_ON_ERROR);
        if ($status < 200 || $status >= 300 || !is_array($data) ||
            (isset($data['error']) && $data['error'] !== [] &&
             (!is_array($data['error']) || ($data['error']['code'] ?? '') !== 'ok'))) {
            throw new RuntimeException('REMOTE_ERROR');
        }
        return $data;
    }

    private static function curl(string $method, string $url, array $headers, ?string $body): array
    {
        $handle = curl_init($url);
        $response = '';
        curl_setopt_array($handle, [
            CURLOPT_CUSTOMREQUEST => $method,
            CURLOPT_HTTPHEADER => $headers,
            CURLOPT_FOLLOWLOCATION => false,
            CURLOPT_PROTOCOLS => CURLPROTO_HTTPS,
            CURLOPT_SSL_VERIFYPEER => true,
            CURLOPT_SSL_VERIFYHOST => 2,
            CURLOPT_CONNECTTIMEOUT => 10,
            CURLOPT_TIMEOUT => 25,
            CURLOPT_WRITEFUNCTION => static function ($handle, string $chunk) use (&$response): int {
                if (strlen($response) + strlen($chunk) > 1048576) { return 0; }
                $response .= $chunk;
                return strlen($chunk);
            },
        ]);
        if ($body !== null) { curl_setopt($handle, CURLOPT_POSTFIELDS, $body); }
        try {
            if (curl_exec($handle) === false) { throw new RuntimeException('NETWORK_ERROR'); }
            return [curl_getinfo($handle, CURLINFO_RESPONSE_CODE), $response];
        } finally {
            curl_close($handle);
        }
    }
}

final class SdkAuthentication extends Authentication
{
    public function __construct(array $config, private Http $http, private string $verifier = '')
    {
        parent::__construct($config);
    }

    public function sendRequest($method, $endpoint, $params)
    {
        if ($this->verifier !== '' && ($params['grant_type'] ?? '') === 'authorization_code') {
            $params['code_verifier'] = $this->verifier;
        }
        return $this->http->send($method, $endpoint, $params);
    }
}

final class SdkUser extends User
{
    public function __construct(array $config, private Http $http) { parent::__construct($config); }

    public function sendRequest($method, $endpoint, $params)
    {
        return $this->http->send($method, $endpoint, $params, $this->accessToken);
    }
}

final class Bridge
{
    private Http $http;

    public function __construct(?Closure $sender = null) { $this->http = new Http($sender); }

    public function dispatch(array $request): array
    {
        if (($request['protocol'] ?? null) !== 1 || !is_string($request['action'] ?? null)) {
            throw new RuntimeException('INVALID_REQUEST');
        }
        $action = $request['action'];
        if ($action === 'health') {
            return ['php_version' => PHP_VERSION, 'sdk_loaded' => class_exists(Authentication::class),
                    'sdk_version' => InstalledVersions::getPrettyVersion('jstolpe/tiktok-api-php-sdk'),
                    'publishing_enabled' => false, 'account_verified' => false];
        }
        if (!in_array($action, ['authorize_url', 'exchange', 'refresh', 'profile'], true)) {
            throw new RuntimeException('ACTION_DISABLED');
        }
        $p = $request['params'] ?? null;
        if (!is_array($p)) { throw new RuntimeException('INVALID_REQUEST'); }
        if ($action === 'profile') {
            $sdk = new SdkUser(['access_token' => self::value($p, 'access_token')], $this->http);
            $data = $sdk->getSelf(['fields' => 'open_id,display_name']);
            $user = $data['data']['user'] ?? [];
            return ['open_id' => self::value($user, 'open_id'),
                    'display_name' => self::value($user, 'display_name')];
        }
        $config = ['client_key' => self::value($p, 'client_key'),
                   'client_secret' => $action === 'authorize_url' ? '' : self::value($p, 'client_secret')];
        $verifier = '';
        if (in_array($action, ['authorize_url', 'exchange'], true)) {
            $redirect = self::value($p, 'redirect_uri');
            $uri = parse_url($redirect);
            $loopback = in_array($uri['host'] ?? '', ['localhost', '127.0.0.1'], true);
            if (strlen($redirect) >= 512 || !$uri || empty($uri['host']) ||
                isset($uri['user']) || isset($uri['pass']) || isset($uri['query']) || isset($uri['fragment']) ||
                !in_array($uri['scheme'] ?? '', $loopback ? ['http', 'https'] : ['https'], true) ||
                ($loopback && empty($uri['port']))) {
                throw new RuntimeException('INVALID_REQUEST');
            }
            if ($loopback) {
                $verifier = self::value($p, 'code_verifier');
                if (!preg_match('/^[A-Za-z0-9._~-]{43,128}$/D', $verifier)) {
                    throw new RuntimeException('INVALID_REQUEST');
                }
            }
        }
        $sdk = new SdkAuthentication($config, $this->http, $verifier);
        if ($action === 'authorize_url') {
            $state = self::value($p, 'state');
            if (!preg_match('/^[A-Za-z0-9_-]{32,128}$/D', $state)) {
                throw new RuntimeException('INVALID_REQUEST');
            }
            $url = $sdk->getAuthenticationUrl($redirect, ['user.info.basic'], $state);
            if ($verifier !== '') {
                $url .= '&' . http_build_query(['code_challenge' => hash('sha256', $verifier),
                                               'code_challenge_method' => 'S256']);
            }
            return ['url' => $url];
        }
        $data = $action === 'exchange'
            ? $sdk->getAccessTokenFromCode(self::value($p, 'code'), $redirect)
            : $sdk->getRefreshAccessToken(self::value($p, 'refresh_token'));
        self::value($data, 'access_token');
        self::value($data, 'refresh_token');
        return array_intersect_key($data, array_flip([
            'access_token', 'refresh_token', 'expires_in', 'refresh_expires_in', 'open_id', 'scope', 'token_type',
        ]));
    }

    private static function value(array $params, string $name): string
    {
        $value = $params[$name] ?? null;
        if (!is_string($value) || trim($value) === '' || strlen($value) > 8192 ||
            preg_match('/[\x00-\x1f\x7f]/', $value)) {
            throw new RuntimeException('INVALID_REQUEST');
        }
        return $value;
    }
}
