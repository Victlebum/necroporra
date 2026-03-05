from django.contrib import admin
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from django.db.models import Count

from .models import Pool, PoolMembership, Celebrity, PoolCelebrity, Prediction


# ========== Site Branding ==========

admin.site.site_header = "Necroporra Administration"
admin.site.site_title = "Necroporra Admin"
admin.site.index_title = "Manage Pools, Celebrities & Predictions"


# ========== Filters ==========

class DeceasedFilter(admin.SimpleListFilter):
    """Filter celebrities by alive/deceased status."""
    title = "status"
    parameter_name = "deceased"

    def lookups(self, request, model_admin):
        return [
            ("yes", "Deceased"),
            ("no", "Alive"),
        ]

    def queryset(self, request, queryset):
        if self.value() == "yes":
            return queryset.filter(death_date__isnull=False)
        if self.value() == "no":
            return queryset.filter(death_date__isnull=True)
        return queryset


class PoolActiveFilter(admin.SimpleListFilter):
    """Filter pools by active/expired status."""
    title = "pool status"
    parameter_name = "active"

    def lookups(self, request, model_admin):
        return [
            ("active", "Active"),
            ("expired", "Expired"),
        ]

    def queryset(self, request, queryset):
        from django.utils import timezone
        now = timezone.now()
        if self.value() == "active":
            return queryset.filter(limit_date__gt=now)
        if self.value() == "expired":
            return queryset.filter(limit_date__lte=now)
        return queryset


class PredictionOutcomeFilter(admin.SimpleListFilter):
    """Filter predictions by outcome."""
    title = "outcome"
    parameter_name = "outcome"

    def lookups(self, request, model_admin):
        return [
            ("correct", "Correct"),
            ("incorrect", "Incorrect"),
            ("pending", "Pending"),
        ]

    def queryset(self, request, queryset):
        if self.value() == "correct":
            return queryset.filter(is_correct=True)
        if self.value() == "incorrect":
            return queryset.filter(is_correct=False)
        if self.value() == "pending":
            return queryset.filter(is_correct__isnull=True)
        return queryset


# ========== Inlines ==========

class PoolMembershipInline(admin.TabularInline):
    model = PoolMembership
    extra = 0
    raw_id_fields = ("user",)
    readonly_fields = ("joined_at",)
    fields = ("user", "wins", "total_points", "joined_at")


class PoolCelebrityInline(admin.TabularInline):
    model = PoolCelebrity
    extra = 0
    raw_id_fields = ("celebrity", "added_by")
    readonly_fields = ("added_at",)
    fields = ("celebrity", "added_by", "is_death_recorded", "manual_death_date", "added_at")


class PredictionInline(admin.TabularInline):
    model = Prediction
    extra = 0
    raw_id_fields = ("user", "celebrity")
    readonly_fields = ("created_at", "is_correct", "points_earned")
    fields = ("user", "celebrity", "weight", "is_correct", "points_earned", "created_at")


# ========== Model Admins ==========

@admin.register(Pool)
class PoolAdmin(admin.ModelAdmin):
    list_display = (
        "name", "slug", "admin", "scoring_mode", "timeframe_choice",
        "is_public", "member_count", "is_active_display", "days_remaining_display",
        "created_at",
    )
    list_filter = ("scoring_mode", "is_public", "timeframe_choice", PoolActiveFilter)
    search_fields = ("name", "slug", "admin__username", "creator__username")
    readonly_fields = ("slug", "created_at", "updated_at", "limit_date", "picks_visibility_date")
    raw_id_fields = ("creator", "admin")
    date_hierarchy = "created_at"
    list_per_page = 25

    fieldsets = (
        (None, {
            "fields": ("name", "description", "slug"),
        }),
        ("Administration", {
            "fields": ("creator", "admin"),
        }),
        ("Timeframe", {
            "fields": ("timeframe_choice", "limit_date"),
        }),
        ("Scoring & Limits", {
            "fields": ("scoring_mode", "max_predictions_per_user"),
        }),
        ("Visibility", {
            "fields": ("is_public", "picks_visible", "picks_visible_after_days", "picks_visibility_date"),
        }),
        ("Timestamps", {
            "fields": ("created_at", "updated_at"),
            "classes": ("collapse",),
        }),
    )

    inlines = [PoolMembershipInline, PoolCelebrityInline]

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(
            _member_count=Count("memberships")
        )

    @admin.display(description="Members", ordering="_member_count")
    def member_count(self, obj):
        return obj._member_count

    @admin.display(description="Active", boolean=True)
    def is_active_display(self, obj):
        return obj.is_pool_active()

    @admin.display(description="Days Left")
    def days_remaining_display(self, obj):
        days = obj.days_remaining()
        if days == 0:
            return "Expired"
        return f"{days}d"


@admin.register(Celebrity)
class CelebrityAdmin(admin.ModelAdmin):
    list_display = (
        "name", "wikidata_link", "birth_date", "death_date",
        "is_deceased_display", "created_at",
    )
    list_filter = (DeceasedFilter,)
    search_fields = ("name", "wikidata_id")
    readonly_fields = ("created_at", "wikidata_link", "image_preview")
    list_per_page = 50

    fieldsets = (
        (None, {
            "fields": ("name", "bio", "image_url", "image_preview"),
        }),
        ("Wikidata", {
            "fields": ("wikidata_id", "wikidata_link"),
        }),
        ("Dates", {
            "fields": ("birth_date", "death_date"),
        }),
        ("Metadata", {
            "fields": ("created_at",),
            "classes": ("collapse",),
        }),
    )

    @admin.display(description="Deceased", boolean=True)
    def is_deceased_display(self, obj):
        return obj.is_deceased()

    @admin.display(description="Wikidata")
    def wikidata_link(self, obj):
        if obj.wikidata_id:
            url = f"https://www.wikidata.org/wiki/{obj.wikidata_id}"
            return format_html('<a href="{}" target="_blank">{}</a>', url, obj.wikidata_id)
        return "-"

    @admin.display(description="Image")
    def image_preview(self, obj):
        if obj.image_url:
            return format_html(
                '<img src="{}" style="max-height: 150px; max-width: 150px; border-radius: 4px;" />',
                obj.image_url,
            )
        return "No image"


@admin.register(PoolMembership)
class PoolMembershipAdmin(admin.ModelAdmin):
    list_display = ("user", "pool", "wins", "total_points", "joined_at")
    list_filter = ("pool",)
    search_fields = ("user__username", "pool__name", "pool__slug")
    raw_id_fields = ("user", "pool")
    readonly_fields = ("joined_at",)
    list_per_page = 50


@admin.register(PoolCelebrity)
class PoolCelebrityAdmin(admin.ModelAdmin):
    list_display = (
        "celebrity", "pool", "added_by", "is_death_recorded",
        "manual_death_date", "added_at",
    )
    list_filter = ("is_death_recorded", "pool")
    search_fields = ("celebrity__name", "pool__name", "pool__slug")
    raw_id_fields = ("pool", "celebrity", "added_by")
    readonly_fields = ("added_at",)
    list_per_page = 50


@admin.register(Prediction)
class PredictionAdmin(admin.ModelAdmin):
    list_display = (
        "user", "pool", "celebrity", "weight",
        "outcome_display", "points_earned", "created_at",
    )
    list_filter = (PredictionOutcomeFilter, "pool")
    search_fields = ("user__username", "celebrity__name", "pool__name", "pool__slug")
    raw_id_fields = ("user", "pool", "celebrity")
    readonly_fields = ("created_at",)
    date_hierarchy = "created_at"
    list_per_page = 50

    @admin.display(description="Outcome")
    def outcome_display(self, obj):
        if obj.is_correct is True:
            return mark_safe('<span style="color: green; font-weight: bold;">&#10003; Correct</span>')
        if obj.is_correct is False:
            return mark_safe('<span style="color: red;">&#10007; Incorrect</span>')
        return mark_safe('<span style="color: gray;">&#8943; Pending</span>')
