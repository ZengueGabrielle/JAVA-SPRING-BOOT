package com.keyce.caroussel;

import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.web.bind.annotation.GetMapping;
import java.io.File;
import java.util.ArrayList;
import java.util.List;

@Controller
public class HomeController {

    @GetMapping("/")
    public String home(Model model) {
        List<String> images = new ArrayList<>();
        
        // Dynamic detection of images in the resources folder
        String path = "src/main/resources/static/images";
        File folder = new File(path);
        
        if (folder.exists() && folder.isDirectory()) {
            File[] listOfFiles = folder.listFiles();
            if (listOfFiles != null) {
                for (File file : listOfFiles) {
                    if (file.isFile()) {
                        String name = file.getName().toLowerCase();
                        if (name.endsWith(".jpg") || name.endsWith(".jpeg") || name.endsWith(".png") || name.endsWith(".webp")) {
                            images.add(file.getName());
                        }
                    }
                }
            }
        }
        
        // Fallback to static list if folder is not found (e.g. when packaged)
        if (images.isEmpty()) {
            images = List.of("accueil.jpg", "messe.jpg", "hopital.jpg", "rencontre.jpg", "depart.jpg");
        }

        model.addAttribute("images", images);
        model.addAttribute("pageTitle", "Visite Historique de Sa Sainteté Léon XIV au Cameroun");
        return "index";
    }
}
