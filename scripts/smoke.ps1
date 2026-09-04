param(
    [string]$BaseUrl = "http://127.0.0.1:8000",
    [switch]$WithModel
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot

$health = Invoke-RestMethod "$BaseUrl/api/health"
if ($health.status -ne "ok" -or -not $health.sqlite_fts5) {
    throw "Health or SQLite FTS5 check failed"
}

$tender = Invoke-RestMethod -Method Post -Uri "$BaseUrl/api/documents" -Form @{
    file = Get-Item "$root/samples/fictional_tender.pdf"
}
$bid = Invoke-RestMethod -Method Post -Uri "$BaseUrl/api/documents" -Form @{
    file = Get-Item "$root/samples/fictional_bid.pdf"
}
$blocks = Invoke-RestMethod "$BaseUrl/api/documents/$($tender.id)/blocks?q=工期要求&context=1"
$shortQueryBlocks = Invoke-RestMethod "$BaseUrl/api/documents/$($tender.id)/blocks?q=工期&context=0"

if ($tender.page_count -lt 1 -or $tender.heading_count -lt 1 -or $tender.paragraph_count -lt 1 -or $tender.table_count -lt 1 -or $bid.page_count -lt 1 -or $blocks.total -lt 1 -or $shortQueryBlocks.total -lt 1) {
    throw "Upload, parse, or FTS search check failed"
}

$invalidRejected = $false
try {
    Invoke-RestMethod -Method Post -Uri "$BaseUrl/api/documents" -Form @{
        file = Get-Item "$root/README.md"
    }
} catch {
    $invalidRejected = [int]$_.Exception.Response.StatusCode -eq 422
}
if (-not $invalidRejected) { throw "Unsupported file was not rejected" }

$review = $null
if ($WithModel) {
    if (-not $health.model_configured) { throw "Model is not configured" }
    $review = Invoke-RestMethod -Method Post -Uri "$BaseUrl/api/reviews" `
        -ContentType "application/json" -Body (@{
            tender_document_id = $tender.id
            bid_document_id = $bid.id
        } | ConvertTo-Json)
    $categories = @($review.requirements | ForEach-Object { $_.category })
    if ($review.status -ne "awaiting_review" -or $review.requirements.Count -lt 3 `
        -or "qualification" -notin $categories -or "timeline" -notin $categories `
        -or "scoring" -notin $categories `
        -or $review.requirement_checks.Count -ne $review.requirements.Count) {
        throw "AI requirement extraction check failed"
    }
    $timeline = $review.requirements | Where-Object category -eq "timeline" | Select-Object -First 1
    $timelineCheck = $review.requirement_checks | Where-Object requirement_id -eq $timeline.id
    if (-not $timelineCheck -or $timelineCheck.match_status -eq "satisfied") {
        throw "Known 180-day versus 150-day conflict was not detected"
    }
    $findingCategories = @($review.findings | ForEach-Object { $_.category })
    if ($review.findings.Count -ne 4 -or "amount" -notin $findingCategories `
        -or "date" -notin $findingCategories -or "project_name" -notin $findingCategories `
        -or "duration" -notin $findingCategories) {
        throw "Deterministic consistency findings check failed"
    }
}

if ($health.libreoffice) {
    $docx = Invoke-RestMethod -Method Post -Uri "$BaseUrl/api/documents" -Form @{
        file = Get-Item "$root/samples/fictional_tender.docx"
    }
    if ($docx.page_count -lt 1 -or $docx.table_count -lt 1) {
        throw "DOCX structure or page parsing check failed"
    }
} else {
    $docxDependencyReported = $false
    try {
        Invoke-RestMethod -Method Post -Uri "$BaseUrl/api/documents" -Form @{
            file = Get-Item "$root/samples/fictional_tender.docx"
        }
    } catch {
        $docxDependencyReported = [int]$_.Exception.Response.StatusCode -eq 422
    }
    if (-not $docxDependencyReported) { throw "Missing LibreOffice was not reported" }
}

[pscustomobject]@{
    Status = "PASS"
    TenderDocumentId = $tender.id
    BidDocumentId = $bid.id
    SearchHitsWithContext = $blocks.total
    ShortChineseSearchHits = $shortQueryBlocks.total
    InvalidFileRejected = $invalidRejected
    LibreOfficeAvailable = $health.libreoffice
    ExtractedRequirements = if ($review) { $review.requirements.Count } else { "skipped" }
    MatchedRequirements = if ($review) { $review.requirement_checks.Count } else { "skipped" }
    ConsistencyFindings = if ($review) { $review.findings.Count } else { "skipped" }
} | Format-List
