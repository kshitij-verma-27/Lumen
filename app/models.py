from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class FacetDefinition(BaseModel):
    id: str = Field(..., description="Unique facet identifier, e.g. 'deadline', 'gpu_tgp', 'tuition_fee'")
    name: str = Field(..., description="Human-readable label, e.g. 'Application Deadline'")
    description: str = Field(..., description="What to extract for this facet")
    expected_type: str = Field("text", description="'currency' | 'unit_number' | 'percentage' | 'date' | 'list' | 'text'")
    importance: str = Field("high", description="'critical' | 'high' | 'medium'")
    consequence: Optional[str] = Field(None, description="One-line real-world impact if missing, conflicting, or wrong")
    is_deadline: bool = Field(False, description="True if this facet represents a deadline, expiration, or cutoff date")


class ResearchSessionCreate(BaseModel):
    goal: str = Field(..., description="The user's research goal or question across ANY topic")
    domain_type: str = Field("custom", description="Template key or 'custom'")
    official_domain: Optional[str] = Field(None, description="Official domain for authority matching (e.g. 'lenovo.com', 'gatech.edu', 'pmsuryaghar.gov.in')")
    target_version_period: Optional[str] = Field(None, description="Optional target version or period (e.g. '2025-26', 'Fall 2025', 'Gen 7', '2025')")
    target_cycle: Optional[str] = Field(None, description="Alias for target_version_period")
    custom_facets: Optional[List[FacetDefinition]] = Field(None, description="Optional list of custom facets")


class GenerateFacetsRequest(BaseModel):
    goal: str = Field(..., description="User's research goal or question")
    domain_type: Optional[str] = Field("custom", description="Optional domain type hint")


class GenerateFacetsResponse(BaseModel):
    goal: str
    suggested_domain: Optional[str] = None
    suggested_official_domain: Optional[str] = None
    facets: List[FacetDefinition]


class UpdateFacetsRequest(BaseModel):
    facets: List[FacetDefinition]


class VersionPeriodOverridePayload(BaseModel):
    target_version_period: Optional[str] = None
    target_cycle: Optional[str] = None


class CycleOverridePayload(BaseModel):
    target_cycle: Optional[str] = None
    target_version_period: Optional[str] = None


class SourceInput(BaseModel):
    url: Optional[str] = None
    pasted_text: Optional[str] = None
    title: Optional[str] = None


class SourcesAddRequest(BaseModel):
    sources: List[SourceInput]


class ClaimResponse(BaseModel):
    id: str
    session_id: str
    source_id: str
    source_title: Optional[str] = None
    source_url: Optional[str] = None
    source_authority: Optional[str] = None
    facet: str
    value_raw: str
    value_normalized: Optional[str] = None
    exact_quote: str
    scope: str
    version_period: Optional[str] = None
    cycle: Optional[str] = None
    verified: bool
    verification_score: float
    quote_offset_start: Optional[int] = None
    quote_offset_end: Optional[int] = None
    rejection_reason: Optional[str] = None
    survived_redteam: bool = True
    redteam_notes: Optional[str] = None


class SourceResponse(BaseModel):
    id: str
    session_id: str
    url: Optional[str] = None
    title: Optional[str] = None
    fetched_at: str
    content_hash: str
    published_date: Optional[str] = None
    published_date_origin: str = "none"
    authority: str
    original_group_id: Optional[str] = None
    fetch_status: str
    error_message: Optional[str] = None
    text_length: int
    text_preview: str


class SessionDetailResponse(BaseModel):
    id: str
    goal: str
    domain_type: str
    official_domain: Optional[str] = None
    target_version_period: Optional[str] = None
    target_cycle: Optional[str] = None
    facets: List[FacetDefinition]
    created_at: str
    sources_count: int
    claims_count: int
    verified_claims_count: int
    rejected_claims_count: int



class HealthStatus(BaseModel):
    status: str
    gemini_configured: bool
    mode: str
    model: str
    database: str
    fallback_reason: Optional[str] = None

