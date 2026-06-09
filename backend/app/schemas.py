from typing import Any, Literal

from pydantic import BaseModel, EmailStr, Field

MatchTier = Literal["exact", "almost", "stretch"]
DishCategory = Literal["main", "side", "salad", "dip"]


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: str
    email: str
    is_guest: bool = False


class UserResponse(BaseModel):
    user_id: str
    email: str
    is_guest: bool = False


class PreferencesResponse(BaseModel):
    diets: list[str] = []
    intolerances: list[str] = []
    health_conditions: list[str] = []
    skill_level: str = "beginner"
    explain_techniques: bool = True
    include_pantry_staples: bool = True
    pantry_staples: list[str] = []
    flavor_profile: dict = {}
    craving_history: list[dict] = []


class PreferencesUpdate(BaseModel):
    diets: list[str] | None = None
    intolerances: list[str] | None = None
    health_conditions: list[str] | None = None
    skill_level: str | None = None
    explain_techniques: bool | None = None
    include_pantry_staples: bool | None = None
    pantry_staples: list[str] | None = None
    flavor_profile: dict | None = None
    craving_history: list[dict] | None = None


class ParseIngredientsRequest(BaseModel):
    text: str = Field(min_length=1, max_length=2000)


class ParseIngredientsResponse(BaseModel):
    ingredients: list[str]
    mock: bool = False


class SearchRecipesRequest(BaseModel):
    ingredients: list[str] = Field(min_length=1)
    diets: list[str] = []
    intolerances: list[str] = []
    health_conditions: list[str] = []
    include_pantry_staples: bool = True
    pantry_staples: list[str] = []


class IngredientMatch(BaseModel):
    name: str
    amount: str | None = None


class RecipeSearchResult(BaseModel):
    id: int
    title: str
    image: str | None = None
    match_tier: MatchTier
    match_label: str
    used_ingredients: list[IngredientMatch]
    missed_ingredients: list[IngredientMatch]
    unused_ingredients: list[IngredientMatch]
    diets: list[str] = []
    ready_in_minutes: int | None = None
    servings: int | None = None
    source_url: str | None = None
    video_url: str | None = None
    summary: str | None = None


class SearchRecipesResponse(BaseModel):
    query_ingredients: list[str]
    effective_ingredients: list[str]
    results: list[RecipeSearchResult]
    mock: bool = False
    message: str | None = None


class RecipeDetailResponse(BaseModel):
    id: int
    title: str
    image: str | None = None
    summary: str | None = None
    ready_in_minutes: int | None = None
    servings: int | None = None
    source_url: str | None = None
    video_url: str | None = None
    ingredients: list[IngredientMatch]
    instructions: list[str]
    diets: list[str] = []
    mock: bool = False


class SimplifyRecipeRequest(BaseModel):
    explain_techniques: bool | None = None
    skill_level: str | None = None
    what_sounds_good: str | None = Field(default=None, max_length=500)
    protein_filters: list[str] = Field(default_factory=list, max_length=5)
    side_filters: list[str] = Field(default_factory=list, max_length=8)
    diets: list[str] = []
    intolerances: list[str] = []
    health_conditions: list[str] = []


class SimplifiedStep(BaseModel):
    step: int
    text: str
    tip: str | None = None


class SimplifyRecipeResponse(BaseModel):
    recipe_id: int
    title: str
    mode: str
    steps: list[SimplifiedStep]
    mock: bool = False


class ElevationInsight(BaseModel):
    heading: str
    body: str


class CompanionRecipe(BaseModel):
    key: str
    title: str
    why: str
    ingredients: list[str] = []
    steps: list[SimplifiedStep] = []


class AccentSide(BaseModel):
    key: str
    title: str
    why: str
    pairs_because: str = ""
    diet_note: str | None = None
    ingredients: list[str] = []
    steps: list[SimplifiedStep] = []


class CookKitRequest(BaseModel):
    explain_techniques: bool | None = None
    skill_level: str | None = None
    what_sounds_good: str | None = Field(default=None, max_length=500)
    dish_anchor: str | None = Field(default=None, max_length=40)
    protein_filters: list[str] = Field(default_factory=list, max_length=5)
    side_filters: list[str] = Field(default_factory=list, max_length=8)
    diets: list[str] = []
    intolerances: list[str] = []
    health_conditions: list[str] = []


class CookKitResponse(BaseModel):
    recipe_id: int
    title: str
    mode: str
    steps: list[SimplifiedStep]
    elevation_insights: list[ElevationInsight] = []
    accent_side: AccentSide | None = None
    companions: list[CompanionRecipe] = []
    dish_anchor: str | None = None
    mock: bool = False


class DietOption(BaseModel):
    value: str
    label: str


class MetaResponse(BaseModel):
    mock_mode: bool
    xai_configured: bool = False
    spoonacular_configured: bool = False
    diets: list[DietOption]
    intolerances: list[DietOption]
    health_conditions: list[DietOption]
    protein_options: list[DietOption] = []
    side_options: list[DietOption] = []
    cuisine_options: list[DietOption] = []


class AdvisorRecipeInput(BaseModel):
    id: int
    title: str
    match_tier: str = "almost"
    match_label: str = ""
    summary: str | None = None
    diets: list[str] = []
    used_ingredients: list[IngredientMatch] = []
    missed_ingredients: list[IngredientMatch] = []


class AdvisorInsightsRequest(BaseModel):
    ingredients: list[str] = Field(min_length=1)
    diets: list[str] = []
    intolerances: list[str] = []
    health_conditions: list[str] = []
    recipes: list[AdvisorRecipeInput] = []
    what_sounds_good: str | None = Field(default=None, max_length=500)
    deeper_insight: bool = False


class AdvisorPick(BaseModel):
    category: str
    title: str
    why: str
    recipe_id: int | None = None


class AdvisorInsightSection(BaseModel):
    heading: str
    body: str


class AdvisorInsightsResponse(BaseModel):
    headline: str
    summary: str
    top_picks: list[AdvisorPick] = []
    sections: list[AdvisorInsightSection] = []
    mock: bool = False
    xai_configured: bool = False
    prompt_version: str | None = None


class CravingThread(BaseModel):
    label: str = ""
    search_terms: list[str] = []
    chef_note: str | None = None


class SharedBridge(BaseModel):
    label: str = ""
    search_terms: list[str] = []
    chef_note: str | None = None


class CravingParsed(BaseModel):
    search_mode: str = "chef"
    craving_threads: list[CravingThread] = []
    shared_bridge: SharedBridge | None = None
    dish_anchor: str | None = None
    dish_queries: list[str] = []
    protein: str | None = None
    protein_query: str | None = None
    ingredients: list[str] = []
    starches: list[str] = []
    flavors: list[str] = []
    cuisine: str | None = None
    mood: str | None = None
    main_query: str = ""
    pairing_queries: list[str] = []
    search_terms: list[str] = []
    needs_protein_prompt: bool = False
    protein_options: list[str] = []


class MealRecipeCard(BaseModel):
    id: int
    title: str
    category: DishCategory
    image: str | None = None
    summary: str | None = None
    fit_note: str | None = None
    thread_label: str | None = None
    is_popular: bool = False
    ready_in_minutes: int | None = None
    servings: int | None = None
    source_url: str | None = None
    diets: list[str] = []
    ingredient_names: list[str] = []


class CravingSearchRequest(BaseModel):
    what_sounds_good: str = Field(min_length=1, max_length=500)
    protein_filter: str | None = Field(default=None, max_length=80)
    protein_filters: list[str] = Field(default_factory=list, max_length=5)
    side_filters: list[str] = Field(default_factory=list, max_length=8)
    cuisine_filters: list[str] = Field(default_factory=list, max_length=5)
    selected_recipe_ids: list[int] = Field(default_factory=list, max_length=5)
    diets: list[str] = []
    intolerances: list[str] = []
    health_conditions: list[str] = []


class CravingSearchResponse(BaseModel):
    what_sounds_good: str
    parsed: CravingParsed
    recipes: list[MealRecipeCard] = []
    chef_headline: str | None = None
    chef_intro: str | None = None
    craving_threads: list[CravingThread] = []
    shared_bridge: SharedBridge | None = None
    page_size: int = 12
    popular_top: int = 3
    candidate_count: int = 0
    refined: bool = False
    mock: bool = False
    live: bool = False
    message: str | None = None


class InspiredIngredientItem(BaseModel):
    key: str
    name: str
    amount: str | None = None
    role: str = "ingredient"
    recipe_id: int
    recipe_title: str


class MixElement(BaseModel):
    from_recipe: str
    borrow: str
    use_it: str


class CreationInsight(BaseModel):
    headline: str
    urge_summary: str
    fusion_idea: str
    mix_elements: list[MixElement] = []
    scratch_meal: str


class InspiredSetupRequest(BaseModel):
    recipe_ids: list[int] = Field(min_length=1)
    what_sounds_good: str | None = Field(default=None, max_length=500)
    protein: str | None = Field(default=None, max_length=80)


class InspiredSetupResponse(BaseModel):
    meal_title: str
    ingredients: list[InspiredIngredientItem]
    recipe_titles: list[str] = []
    creation_insight: CreationInsight | None = None
    mock: bool = False


class SubstitutionItem(BaseModel):
    original_key: str
    original_name: str
    substitute: str
    purpose: str
    note: str


class InspiredSubstitutionsRequest(BaseModel):
    recipe_ids: list[int] = Field(min_length=1)
    available_keys: list[str] = []
    what_sounds_good: str | None = Field(default=None, max_length=500)


class InspiredSubstitutionsResponse(BaseModel):
    substitutions: list[SubstitutionItem] = []
    mock: bool = False


class ApprovedSubstitution(BaseModel):
    original_key: str
    original_name: str
    substitute: str


class ChefProposal(BaseModel):
    dish_name: str
    pitch: str
    technique_highlight: str
    plate_description: str
    pantry_note: str = ""


class InspiredCookRequest(BaseModel):
    recipe_ids: list[int] = Field(min_length=1)
    available_keys: list[str] = []
    approved_substitutions: list[ApprovedSubstitution] = []
    explain_techniques: bool = True
    what_sounds_good: str | None = Field(default=None, max_length=500)
    chef_proposal: ChefProposal | None = None


class InspiredCookResponse(BaseModel):
    meal_title: str
    steps: list[SimplifiedStep]
    substitutions_applied: list[ApprovedSubstitution] = []
    chef_proposal: ChefProposal | None = None
    mock: bool = False


class InspiredProposalRequest(BaseModel):
    recipe_ids: list[int] = Field(min_length=1)
    available_keys: list[str] = []
    approved_substitutions: list[ApprovedSubstitution] = []
    what_sounds_good: str | None = Field(default=None, max_length=500)


class InspiredProposalResponse(BaseModel):
    proposal: ChefProposal
    mock: bool = False


class SaveRecipeRequest(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    what_sounds_good: str | None = Field(default=None, max_length=500)
    recipe_ids: list[int] = Field(default_factory=list)
    steps: list[SimplifiedStep] = Field(min_length=1)
    substitutions_applied: list[ApprovedSubstitution] = []
    chef_proposal: ChefProposal | None = None


class SavedRecipeSummary(BaseModel):
    id: str
    title: str
    what_sounds_good: str | None = None
    recipe_count: int = 0
    step_count: int = 0
    created_at: str


class SavedRecipeDetail(BaseModel):
    id: str
    title: str
    what_sounds_good: str | None = None
    recipe_ids: list[int] = []
    steps: list[SimplifiedStep] = []
    substitutions_applied: list[ApprovedSubstitution] = []
    chef_proposal: ChefProposal | None = None
    created_at: str


class SaveRecipeResponse(BaseModel):
    id: str
    message: str = "Recipe saved to your personal file."