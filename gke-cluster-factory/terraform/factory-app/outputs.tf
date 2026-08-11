output "portal_url" {
  value = google_cloud_run_v2_service.portal.uri
}
   
output "portal_service_account" {
  value = google_service_account.portal.email
}
