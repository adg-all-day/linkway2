from django.urls import path

from .views import GenerateContentView, GenerateImageView, GenerateRecommendationsView

urlpatterns = [
    path("content/", GenerateContentView.as_view(), name="ai-generate-content"),
    path("images/", GenerateImageView.as_view(), name="ai-generate-image"),
    path("recommendations/", GenerateRecommendationsView.as_view(), name="ai-generate-recommendations"),
]
