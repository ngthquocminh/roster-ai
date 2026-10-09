// CloudFront Function (cloudfront-js-2.0), viewer-request, default behavior only.
// React Router deep links (/scenario-data) have no object in S3, so any URI whose
// last path segment has no "." is served as /index.html. Paths with a "." (assets,
// favicon, missing files) pass through unchanged and keep S3's own 403/404.
// The /api/* behavior has no function, and the distribution has no
// custom_error_response, so the API's own 401/403/404 responses are never rewritten.
function handler(event) {
  var request = event.request;
  var uri = request.uri;
  var lastSegment = uri.substring(uri.lastIndexOf('/') + 1);

  if (lastSegment.indexOf('.') === -1) {
    request.uri = '/index.html';
  }

  return request;
}
