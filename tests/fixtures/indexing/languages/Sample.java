import java.util.List;

@Entity
@Table(name = "accounts")
public class Sample {
    @Test
    public void loadsAccounts() {
    }

    @GetMapping("/accounts")
    public List<String> accounts() {
        return List.of();
    }
}
